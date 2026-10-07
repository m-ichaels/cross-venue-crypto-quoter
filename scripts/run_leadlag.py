#!/usr/bin/env python3
"""Hayashi-Yoshida lead-lag between the three venues' mids -> results/leadlag.json and results/leadlag_curves.csv.

    python scripts/run_leadlag.py [--derived data/derived] [--grid-ms 2000] [--step-ms 20] [--block-s 600] [--n-boot 300]

Three clock variants per pair:
  exchange   each venue's own event time (matching-engine timestamps; assumes the exchanges' clocks agree)
  receive    the recorder's receive time for both legs (one clock, but each leg carries its own network delay)
  bookticker Binance's real-time bookTicker stream (receive time) against the other venue's receive time
theta* > 0 means the first-named venue leads. Blocks of `block_s` seconds are the bootstrap unit. The script also
writes `leader_for`: for every venue, the other venue with the largest lead-lag ratio against it (exchange clock),
which the replay's re-marking signal uses as its reference.
"""
import argparse
import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cvq import books  # noqa: E402
from cvq.vendor import leadlag as LL  # noqa: E402

VENUES = ("binance", "coinbase", "bitstamp")


def mid_series(derived, venue, clock, hours=None):
    bbo = books.load_concat(derived, venue, "bbo", hours)
    t = bbo[clock].to_numpy(np.int64)
    mid = (0.5 * (bbo.bid + bbo.ask)).to_numpy()
    return t, mid


def run_pair(tx_ns, x_px, ty_ns, y_px, origin_ns, grid, block_s, n_boot):
    tx, x = LL.series_from_ticks(tx_ns, x_px, origin_ns)
    ty, y = LL.series_from_ticks(ty_ns, y_px, origin_ns)
    bx = (tx // block_s).astype(int)
    by = (ty // block_s).astype(int)
    covs, sxs, sys_, used = LL.per_block(tx, x, ty, y, bx, by, grid)
    out, pooled = LL.bootstrap(covs, sxs, sys_, grid, n_boot=n_boot, seed=0)
    out["n_obs_x"], out["n_obs_y"] = int(len(tx)), int(len(ty))
    return out, pooled


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--derived", default=os.path.join(ROOT, "data", "derived"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "leadlag.json"))
    ap.add_argument("--curves", default=os.path.join(ROOT, "results", "leadlag_curves.csv"))
    ap.add_argument("--grid-ms", type=int, default=2000)
    ap.add_argument("--step-ms", type=int, default=20)
    ap.add_argument("--block-s", type=float, default=600.0)
    ap.add_argument("--n-boot", type=int, default=300)
    ap.add_argument("--hours", nargs="*", default=None)
    args = ap.parse_args(argv)
    t0 = time.time()
    grid = np.arange(-args.grid_ms, args.grid_ms + 1e-9, args.step_ms) / 1000.0
    series = {}
    for v in VENUES:
        for clock in ("ts", "rx"):
            series[(v, clock)] = mid_series(args.derived, v, clock, args.hours)
    have_bt = bool(books.hours(args.derived, "binance_bbo"))
    if have_bt:
        series[("binance_bbo", "rx")] = mid_series(args.derived, "binance_bbo", "rx", args.hours)
    origin = min(int(s[0][0]) for s in series.values() if len(s[0]))
    results, curves = [], []
    variants = [("exchange", "ts", None), ("receive", "rx", None)] + ([("bookticker", "rx", "binance_bbo")] if have_bt else [])
    for a, b in itertools.combinations(VENUES, 2):
        for name, clock, bt in variants:
            va = bt if (bt and a == "binance") else a
            vb = bt if (bt and b == "binance") else b
            if bt and "binance" not in (a, b):
                continue
            tx, x = series[(va, clock)]
            ty, y = series[(vb, clock)]
            out, pooled = run_pair(tx, x, ty, y, origin, grid, args.block_s, args.n_boot)
            rec = {"pair": f"{a} vs {b}", "x": a, "y": b, "variant": name, **out}
            results.append(rec)
            if pooled is not None:
                for th, rho in zip(pooled.theta, pooled.rho):
                    curves.append({"pair": rec["pair"], "variant": name, "theta_ms": round(th * 1000), "rho": rho})
            print(f"{a} vs {b} [{name}]: theta* {out.get('theta_star', np.nan) * 1000:.0f} ms "
                  f"[{out.get('theta_lo', np.nan) * 1000:.0f}, {out.get('theta_hi', np.nan) * 1000:.0f}], "
                  f"LLR {out.get('llr', np.nan):.2f} [{out.get('llr_lo', np.nan):.2f}, {out.get('llr_hi', np.nan):.2f}], "
                  f"rho* {out.get('rho_star', np.nan):.3f}, rho(0) {out.get('rho_0', np.nan):.3f}, blocks {out.get('n_blocks')}", flush=True)
    # who leads whom (exchange clock): LLR(a vs b) > 1 means a leads b
    lead = {}
    for r in results:
        if r["variant"] != "exchange":
            continue
        lead[(r["x"], r["y"])] = r["llr"]
        lead[(r["y"], r["x"])] = 1.0 / r["llr"] if r["llr"] > 0 else np.inf
    leader_for = {}
    for v in VENUES:
        others = [u for u in VENUES if u != v]
        leader_for[v] = max(others, key=lambda u: lead.get((u, v), 0.0))
    # cross-venue mid differences (basis) on a 1 s grid, exchange clock
    t_lo = max(int(series[(v, "ts")][0][0]) for v in VENUES)
    t_hi = min(int(series[(v, "ts")][0][-1]) for v in VENUES)
    g = np.arange(t_lo, t_hi, 10**9, dtype=np.int64)
    mids = {v: LL.sample_previous_tick(series[(v, "ts")][0], series[(v, "ts")][1], g) for v in VENUES}
    basis = {}
    for a, b in itertools.combinations(VENUES, 2):
        d = (mids[a] - mids[b]) / mids[b] * 1e4
        basis[f"{a} - {b}"] = {"mean_bp": float(np.nanmean(d)), "sd_bp": float(np.nanstd(d)), "p5_bp": float(np.nanpercentile(d, 5)),
                               "p95_bp": float(np.nanpercentile(d, 95))}
    out = {"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0, 1),
           "grid_ms": args.grid_ms, "step_ms": args.step_ms, "block_s": args.block_s, "n_boot": args.n_boot,
           "results": results, "leader_for": leader_for, "basis_bp": basis,
           "mid_changes": {f"{v}:{c}": int(len(LL.series_from_ticks(series[(v, c)][0], series[(v, c)][1], origin)[0])) for (v, c) in series}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="
") as f:
        json.dump(out, f, indent=1, default=float)
    pd.DataFrame(curves).to_csv(args.curves, index=False, lineterminator="
")
    print("leader_for", leader_for, f"({time.time() - t0:.0f} s) -> {args.out}")


if __name__ == "__main__":
    main()
