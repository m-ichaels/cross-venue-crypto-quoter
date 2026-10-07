#!/usr/bin/env python3
"""Replay the quoter on every venue under every configuration, attribute the P&L per fill at two maker-fee tiers,
bootstrap the intervals over episodes, and write results/replay.json plus one fills file per pass.

    python scripts/run_replay.py [--derived data/derived] [--fills data/fills] [--out results/replay.json]
                                 [--latencies 0 50 200] [--base-latency 50] [--queue-models naive_fifo power_prob risk_averse]
                                 [--c-delta 0.5] [--sens-c-delta 0.25 1.0] [--n-boot 2000] [--hours ...]

The leader used by the re-marking signal comes from results/leadlag.json (`leader_for`) when it exists, else Binance
leads the other two and Coinbase is Binance's reference. Fees come from configs/fees.json.
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
from cvq import books, pnl, replay  # noqa: E402
from cvq.quoter import QuoterParams  # noqa: E402

VENUES = ("binance", "coinbase", "bitstamp")
DEFAULT_LEADER = {"binance": "coinbase", "coinbase": "binance", "bitstamp": "binance"}


def load_fees(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def tier_summary(f_att: pd.DataFrame, n_boot: int, seed: int) -> dict:
    out = {}
    for col, name in (("pnl_bp", "pnl"), ("spread_bp", "spread"), ("adverse_bp", "adverse"), ("inventory_bp", "inventory"),
                      ("hold_bp", "hold"), ("liq_bp", "liquidation"), ("fee_bp", "fee")):
        out[name] = pnl.bootstrap_weighted(f_att, col, n_boot=n_boot, seed=seed)
    return out


def pass_summary(res: dict, own_ts, own_mid, fees_v: dict, lot: float, n_boot: int, seed: int) -> tuple[dict, pd.DataFrame]:
    fills = pnl.add_markouts(res["fills"], res["episodes"], own_ts, own_mid)
    ep = res["episodes"]
    hours = (ep["t_end"].max() - (ep["t_end"].min() - 900 * pnl.NS)) / 3.6e12 if len(ep) else np.nan
    summ = {"n_fills": int(len(fills)), "qty_filled_btc": float(fills["qty"].sum()) if len(fills) else 0.0,
            "fills_per_hour": float(len(fills) / hours) if hours and hours > 0 else np.nan,
            "n_episodes": int(len(ep)), "reasons": fills["reason"].value_counts().to_dict() if len(fills) else {},
            "median_age_s": float(fills["age_s"].median()) if len(fills) else np.nan,
            "mean_abs_inventory_lots": float(fills["inv_after_lots"].abs().mean()) if len(fills) else np.nan,
            "max_abs_inventory_lots": float(fills["inv_after_lots"].abs().max()) if len(fills) else np.nan,
            "markouts": {}, "tiers": {}, "stats": res["stats"]}
    for h in pnl.HORIZONS:
        col = f"markout_{h}s_bp"
        if len(fills):
            fills["notional"] = fills["qty"] * fills["price"]
            summ["markouts"][f"{h}s"] = pnl.bootstrap_weighted(fills, col, n_boot=n_boot, seed=seed)
    tier_frames = {}
    for tier, spec in fees_v["tiers"].items():
        att = pnl.attribute(fills, ep, spec["maker_bp"], spec["taker_bp"], lot)
        summ["tiers"][tier] = tier_summary(att, n_boot, seed)
        summ["tiers"][tier]["label"] = spec["label"]
        summ["tiers"][tier]["maker_bp"] = spec["maker_bp"]
        summ["tiers"][tier]["identity_gap_usd"] = pnl.episode_pnl_check(att, ep, lot, spec["taker_bp"])
        tier_frames[tier] = att
    # one fills table with the tier-specific columns side by side
    base = fills
    for tier, att in tier_frames.items():
        for c in ("spread_bp", "adverse_bp", "hold_bp", "liq_bp", "inventory_bp", "fee_bp", "pnl_bp"):
            base[f"{tier}_{c}"] = att[c]
    return summ, base


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--derived", default=os.path.join(ROOT, "data", "derived"))
    ap.add_argument("--fills", default=os.path.join(ROOT, "data", "fills"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "replay.json"))
    ap.add_argument("--fees", default=os.path.join(ROOT, "configs", "fees.json"))
    ap.add_argument("--leadlag", default=os.path.join(ROOT, "results", "leadlag.json"))
    ap.add_argument("--venues", nargs="*", default=list(VENUES))
    ap.add_argument("--latencies", nargs="*", type=int, default=[0, 50, 200])
    ap.add_argument("--base-latency", type=int, default=50)
    ap.add_argument("--queue-models", nargs="*", default=["naive_fifo", "power_prob", "risk_averse"])
    ap.add_argument("--c-delta", type=float, default=0.5)
    ap.add_argument("--sens-c-delta", nargs="*", type=float, default=[0.25, 1.0, 2.0])
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--hours", nargs="*", default=None)
    ap.add_argument("--quick", action="store_true", help="base configuration only")
    args = ap.parse_args(argv)
    t0 = time.time()
    fees = load_fees(args.fees)
    leader_for = dict(DEFAULT_LEADER)
    if os.path.exists(args.leadlag):
        with open(args.leadlag, encoding="utf-8") as f:
            ll = json.load(f)
        leader_for.update(ll.get("leader_for", {}))
    os.makedirs(args.fills, exist_ok=True)
    base_qm = args.queue_models[0]
    configs = []
    for venue in args.venues:
        for signal in (0, 1):
            configs.append((venue, signal, args.base_latency, base_qm, args.c_delta))
            if args.quick:
                continue
            for lat in args.latencies:
                if lat != args.base_latency:
                    configs.append((venue, signal, lat, base_qm, args.c_delta))
            for qm in args.queue_models[1:] + (["l3_exact"] if venue == "bitstamp" else []):
                configs.append((venue, signal, args.base_latency, qm, args.c_delta))
            for cd in args.sens_c_delta:
                configs.append((venue, signal, args.base_latency, base_qm, cd))
    passes = []
    frames = {}
    own_cache = {}
    for (venue, signal, lat, qm, cd) in configs:
        prm = QuoterParams(signal=signal, latency_ms=lat, c_delta=cd)
        leader = leader_for[venue]
        print(f"replay {venue} signal={signal} latency={lat} queue={qm} c_delta={cd} leader={leader}", flush=True)
        res = replay.run(args.derived, venue, prm, queue_model=qm, leader=leader, hours=args.hours)
        if venue not in own_cache:
            own = books.load_concat(args.derived, venue, "bbo", args.hours).sort_values("ts", kind="stable")
            own_cache[venue] = (own.ts.to_numpy(np.int64), (0.5 * (own.bid + own.ask)).to_numpy())
        own_ts, own_mid = own_cache[venue]
        summ, fills = pass_summary(res, own_ts, own_mid, fees["venues"][venue], prm.lot, args.n_boot, seed=1)
        key = f"{venue}_sig{signal}_lat{lat}_{qm}_cd{cd:g}"
        fills.to_parquet(os.path.join(args.fills, key + ".parquet"), index=False)
        res["episodes"].to_parquet(os.path.join(args.fills, key + "_episodes.parquet"), index=False)
        frames[key] = fills
        passes.append({"key": key, "venue": venue, "signal": signal, "latency_ms": lat, "queue_model": qm, "c_delta": cd,
                       "leader": leader, **summ})
        p = summ["tiers"]
        print("   fills %d (%.0f/h)  entry %.2f [%.2f, %.2f]  top %.2f [%.2f, %.2f] bp  (%.1f s)" % (
            summ["n_fills"], summ["fills_per_hour"], p["entry"]["pnl"]["mean"], p["entry"]["pnl"]["lo"], p["entry"]["pnl"]["hi"],
            p["top"]["pnl"]["mean"], p["top"]["pnl"]["lo"], p["top"]["pnl"]["hi"], res["stats"]["seconds"]), flush=True)
    # the re-marking effect: paired difference signal on - off, base configuration, per venue and tier
    effect = {}
    for venue in args.venues:
        k1 = f"{venue}_sig1_lat{args.base_latency}_{base_qm}_cd{args.c_delta:g}"
        k0 = f"{venue}_sig0_lat{args.base_latency}_{base_qm}_cd{args.c_delta:g}"
        if k1 in frames and k0 in frames:
            effect[venue] = {}
            for tier in fees["venues"][venue]["tiers"]:
                a, b = frames[k1].copy(), frames[k0].copy()
                a["pnl_bp"], b["pnl_bp"] = a[f"{tier}_pnl_bp"], b[f"{tier}_pnl_bp"]
                effect[venue][tier] = pnl.bootstrap_difference(a, b, "pnl_bp", n_boot=args.n_boot, seed=2)
            a, b = frames[k1].copy(), frames[k0].copy()
            effect[venue]["adverse_60s"] = pnl.bootstrap_difference(a.assign(x=a["entry_adverse_bp"]), b.assign(x=b["entry_adverse_bp"]), "x", n_boot=args.n_boot, seed=3)
    hours = books.hours(args.derived, args.venues[0])
    out = {"built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": round(time.time() - t0, 1),
           "params": json.loads(QuoterParams(latency_ms=args.base_latency, c_delta=args.c_delta).to_json()),
           "base_queue_model": base_qm, "leader_for": leader_for, "hours": hours, "fees_file": os.path.relpath(args.fees, ROOT),
           "passes": passes, "signal_effect": effect}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1, default=float)
    print(f"done: {len(passes)} passes in {time.time() - t0:.0f} s -> {args.out}")


if __name__ == "__main__":
    main()
