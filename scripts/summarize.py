#!/usr/bin/env python3
"""results/summary.md from results/replay.json, results/leadlag.json and results/books.json.

    python scripts/summarize.py [--check]     (--check renders without writing and fails if a results file is missing)
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")


def f(x, d=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:.{d}f}"


def ci(b, d=2):
    if not b or b.get("mean") is None or not np.isfinite(b.get("mean", np.nan)):
        return "—"
    return f"{b['mean']:.{d}f} [{b['lo']:.{d}f}, {b['hi']:.{d}f}]"


def dci(b, d=2):
    if not b or not np.isfinite(b.get("diff", np.nan)):
        return "—"
    return f"{b['diff']:+.{d}f} [{b['lo']:+.{d}f}, {b['hi']:+.{d}f}]"


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load():
    out = {}
    for name in ("replay", "leadlag", "books"):
        p = os.path.join(RES, f"{name}.json")
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        with open(p, encoding="utf-8") as fh:
            out[name] = json.load(fh)
    return out


def find(passes, venue, signal, latency, qm, cd):
    for p in passes:
        if p["venue"] == venue and p["signal"] == signal and p["latency_ms"] == latency and p["queue_model"] == qm and abs(p["c_delta"] - cd) < 1e-9:
            return p
    return None


VENUE_NAME = {"binance": "Binance BTCUSDT", "coinbase": "Coinbase BTC-USD", "bitstamp": "Bitstamp BTC/USD"}


def render(R: dict) -> str:
    rp, ll, bk = R["replay"], R["leadlag"], R["books"]
    prm = rp["params"]
    base_lat, base_qm, base_cd = prm["latency_ms"], rp["base_queue_model"], prm["c_delta"]
    passes = rp["passes"]
    venues = [v for v in ("binance", "coinbase", "bitstamp") if any(p["venue"] == v for p in passes)]
    L = []
    L.append(f"# cross-venue-crypto-quoter — run summary (built {rp['built_utc']})\n")
    # ---- session
    hours = {}
    for h in bk["hours"]:
        hours.setdefault(h["venue"], []).append(h)
    L.append("## Recording\n")
    L.append("| venue | hour files | raw lines | raw MB (gzip) | depth msgs | trades | gaps | resyncs | notes |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for v, hs in hours.items():
        lines = sum(h["lines"] for h in hs)
        mb = sum(h["raw_bytes"] for h in hs) / 1e6
        depth = sum(h.get("depth", h.get("orders", h.get("bbo", 0))) for h in hs)
        trades = sum(h.get("trades", 0) for h in hs)
        gaps = sum(h.get("gaps", 0) for h in hs)
        resyncs = sum(h.get("resyncs", 0) for h in hs)
        notes = []
        if v == "bitstamp":
            notes.append(f"L3 orders; unknown deletes {sum(h.get('unknown_delete', 0) for h in hs)}; crossed-book messages skipped {sum(h.get('crossed', 0) for h in hs)}")
        if any(h.get("truncated") for h in hs):
            notes.append("last file truncated")
        L.append(f"| {v} | {len(hs)} ({hs[0]['hour']} .. {hs[-1]['hour']}) | {lines:,} | {mb:.1f} | {depth:,} | {trades:,} | {gaps} | {resyncs} | {'; '.join(notes)} |")
    L.append("")
    # ---- headline
    L.append(f"## P&L per fill (bp of notional; base: latency {base_lat} ms, queue model {base_qm}, c_delta {base_cd}; 95 % intervals from resampling {prm['episode_s'] / 60:.0f}-minute episodes)\n")
    L.append("| venue | signal | fills | fills / h | entry tier | P&L entry | top tier | P&L top | mark-out 60 s | median age (s) |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for v in venues:
        for sig in (0, 1):
            p = find(passes, v, sig, base_lat, base_qm, base_cd)
            if p is None:
                continue
            t = p["tiers"]
            L.append(f"| {VENUE_NAME[v]} | {'re-marked off ' + p['leader'] if sig else 'own mid'} | {p['n_fills']} | {f(p['fills_per_hour'], 0)} | "
                     f"{t['entry']['label']} ({f(t['entry']['maker_bp'], 1)} bp) | {ci(t['entry']['pnl'])} | {t['top']['label']} ({f(t['top']['maker_bp'], 1)} bp) | {ci(t['top']['pnl'])} | "
                     f"{ci(p['markouts'].get('60s'))} | {f(p['median_age_s'], 1)} |")
    L.append("")
    L.append("### Re-marking effect (signal on minus off, paired by episode)\n")
    L.append("| venue | leader | ΔP&L entry tier | ΔP&L top tier | Δ adverse selection 60 s |")
    L.append("|---|---|---|---|---|")
    for v in venues:
        e = rp["signal_effect"].get(v)
        if e:
            L.append(f"| {VENUE_NAME[v]} | {rp['leader_for'][v]} | {dci(e.get('entry'))} | {dci(e.get('top'))} | {dci(e.get('adverse_60s'))} |")
    L.append("")
    # ---- attribution
    L.append("## Attribution per fill (bp; base configuration, own mid)\n")
    L.append("| venue | tier | spread capture | − adverse selection (60 s) | − inventory (hold to episode end + flattening) | − fee | = P&L | identity gap (USD) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for v in venues:
        p = find(passes, v, 0, base_lat, base_qm, base_cd)
        if p is None:
            continue
        for tier in ("entry", "top"):
            t = p["tiers"][tier]
            L.append(f"| {VENUE_NAME[v]} | {t['label']} | {ci(t['spread'])} | {ci(t['adverse'])} | {ci(t['inventory'])} | {f(t['fee']['mean'], 1)} | {ci(t['pnl'])} | {t['identity_gap_usd']:.2e} |")
    L.append("")
    L.append("## Mark-outs of the fills (bp, positive = the fill made money against the later mid)\n")
    L.append("| venue | signal | 1 s | 10 s | 60 s | fill reasons |")
    L.append("|---|---|---|---|---|---|")
    for v in venues:
        for sig in (0, 1):
            p = find(passes, v, sig, base_lat, base_qm, base_cd)
            if p is None:
                continue
            reasons = ", ".join(f"{k} {n}" for k, n in sorted(p["reasons"].items(), key=lambda kv: -kv[1]))
            L.append(f"| {VENUE_NAME[v]} | {'on' if sig else 'off'} | {ci(p['markouts'].get('1s'))} | {ci(p['markouts'].get('10s'))} | {ci(p['markouts'].get('60s'))} | {reasons} |")
    L.append("")
    # ---- sensitivity
    L.append("## Sensitivity (top tier P&L per fill, bp; own mid unless stated)\n")
    L.append("| venue | configuration | fills | P&L top, signal off | P&L top, signal on |")
    L.append("|---|---|---|---|---|")
    for v in venues:
        rows = []
        for p in passes:
            if p["venue"] != v or p["signal"] != 0:
                continue
            q = find(passes, v, 1, p["latency_ms"], p["queue_model"], p["c_delta"])
            label = f"latency {p['latency_ms']} ms, {p['queue_model']}, c_delta {p['c_delta']:g}"
            rows.append((p["latency_ms"], p["queue_model"], p["c_delta"], label, p, q))
        for _, _, _, label, p, q in sorted(rows, key=lambda r: (r[2], r[0], r[1])):
            L.append(f"| {VENUE_NAME[v]} | {label} | {p['n_fills']} | {ci(p['tiers']['top']['pnl'])} | {ci(q['tiers']['top']['pnl']) if q else '—'} |")
    L.append("")
    # ---- lead-lag
    L.append(f"## Lead-lag between the venues' mids (Hayashi-Yoshida; theta* > 0: the first venue leads; grid ±{ll['grid_ms']} ms step {ll['step_ms']} ms; {ll['block_s'] / 60:.0f}-minute blocks)\n")
    L.append("| pair | clock | theta* (ms) [95 %] | LLR [95 %] | rho* | rho(0) | P(first leads) | blocks | mid changes |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in ll["results"]:
        L.append(f"| {r['pair']} | {r['variant']} | {r['theta_star'] * 1000:.0f} [{r['theta_lo'] * 1000:.0f}, {r['theta_hi'] * 1000:.0f}] | "
                 f"{f(r['llr'])} [{f(r['llr_lo'])}, {f(r['llr_hi'])}] | {f(r['rho_star'], 3)} | {f(r['rho_0'], 3)} | {f(r['p_x_leads'])} | {r['n_blocks']} | {r['n_obs_x']:,} / {r['n_obs_y']:,} |")
    L.append("")
    L.append("Leader used by the re-marking signal (largest LLR against the venue, exchange clock): " +
             ", ".join(f"{v} ← {u}" for v, u in ll["leader_for"].items()) + ".\n")
    L.append("Cross-venue mid difference on a 1-second grid (bp): " +
             "; ".join(f"{k}: mean {b['mean_bp']:.1f}, sd {b['sd_bp']:.1f}, 5–95 % [{b['p5_bp']:.1f}, {b['p95_bp']:.1f}]" for k, b in ll["basis_bp"].items()) + ".\n")
    L.append(f"Quoter parameters: {json.dumps(prm)}\n")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=os.path.join(RES, "summary.md"))
    args = ap.parse_args(argv)
    text = render(load())
    if args.check:
        print(f"summary renders: {len(text.splitlines())} lines")
        return
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
