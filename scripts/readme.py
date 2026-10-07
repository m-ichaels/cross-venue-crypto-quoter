#!/usr/bin/env python3
"""README.md from scripts/README.template.md and the results files, so every number in the README is the run's.

    python scripts/readme.py [--check]     (--check renders without writing and fails on an unfilled placeholder)
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import summarize as S  # noqa: E402

VENUES = ("binance", "coinbase", "bitstamp")
NAME = {"binance": "Binance", "coinbase": "Coinbase", "bitstamp": "Bitstamp"}


def utc(ns):
    return datetime.fromtimestamp(ns / 1e9, tz=timezone.utc).strftime("%H:%M")


def sign_word(b, unit="bp"):
    """'nets +0.3 [+0.1, +0.5] bp' / 'nets -1.2 [...] bp' / 'nets -0.1 [...] bp, indistinguishable from zero'."""
    if not b or not np.isfinite(b.get("mean", np.nan)):
        return "—"
    s = f"{b['mean']:+.2f} [{b['lo']:+.2f}, {b['hi']:+.2f}]"
    if b["lo"] > 0 or b["hi"] < 0:
        return f"nets {s} {unit}"
    return f"nets {s} {unit}, indistinguishable from zero"


def effect_word(d):
    if not d or not np.isfinite(d.get("diff", np.nan)):
        return "—"
    s = S.dci(d)
    if d["lo"] > 0:
        return f"adds {s} bp"
    if d["hi"] < 0:
        return f"costs {s} bp"
    return f"changes nothing measurable ({s} bp)"


def build_values():
    R = S.load()
    rp, ll, bk = R["replay"], R["leadlag"], R["books"]
    prm = rp["params"]
    lat, qm, cd = prm["latency_ms"], rp["base_queue_model"], prm["c_delta"]
    passes = rp["passes"]
    V = {}
    # ---- recording
    hours = {}
    for h in bk["hours"]:
        hours.setdefault(h["venue"], []).append(h)
    hs = hours.get("binance", [])
    V["rec_date"] = hs[0]["hour"][:10] if hs else "—"
    V["n_hour_files"] = str(len(hs))
    V["raw_mb_total"] = f"{sum(h['raw_bytes'] for v in hours for h in hours[v]) / 1e6:.0f}"
    V["raw_lines_total"] = f"{sum(h['lines'] for v in hours for h in hours[v]):,}"
    for v, hh in hours.items():
        V[f"{v}_raw_mb"] = f"{sum(h['raw_bytes'] for h in hh) / 1e6:.0f}"
        V[f"{v}_lines"] = f"{sum(h['lines'] for h in hh):,}"
        V[f"{v}_trades"] = f"{sum(h.get('trades', 0) for h in hh):,}"
        V[f"{v}_depth"] = f"{sum(h.get('depth', h.get('orders', h.get('bbo', 0))) for h in hh):,}"
        V[f"{v}_gaps"] = str(sum(h.get("gaps", 0) for h in hh))
        V[f"{v}_resyncs"] = str(sum(h.get("resyncs", 0) for h in hh))
        V[f"{v}_bbo_rows"] = f"{sum(h.get('rows_bbo', 0) for h in hh):,}"
    V["bitstamp_unknown_deletes"] = str(sum(h.get("unknown_delete", 0) for h in hours.get("bitstamp", [])))
    # session span from the base pass episodes
    p0 = S.find(passes, "binance", 0, lat, qm, cd)
    V["session_hours"] = f"{p0['n_episodes'] * prm['episode_s'] / 3600:.1f}" if p0 else "—"
    V["n_episodes"] = str(p0["n_episodes"]) if p0 else "—"
    V["episode_min"] = f"{prm['episode_s'] / 60:.0f}"
    # ---- parameters
    for k in ("lot", "c_delta", "c_q", "T", "requote_tol_bp", "max_inventory", "decision_ms", "vol_halflife_s", "basis_halflife_s", "latency_ms"):
        V[f"prm_{k}"] = f"{prm[k]:g}"
    V["base_qm"] = qm
    V["lot_btc"] = f"{prm['lot']:g}"
    # ---- headline per venue
    for v in VENUES:
        for sig in (0, 1):
            p = S.find(passes, v, sig, lat, qm, cd)
            if p is None:
                continue
            t = p["tiers"]
            V[f"{v}_fills_sig{sig}"] = str(p["n_fills"])
            V[f"{v}_fph_sig{sig}"] = f"{p['fills_per_hour']:.0f}"
            V[f"{v}_age_sig{sig}"] = f"{p['median_age_s']:.1f}"
            for tier in ("entry", "top"):
                V[f"{v}_{tier}_pnl_sig{sig}"] = S.ci(t[tier]["pnl"])
                V[f"{v}_{tier}_word_sig{sig}"] = sign_word(t[tier]["pnl"])
                V[f"{v}_{tier}_label"] = t[tier]["label"]
                V[f"{v}_{tier}_bp"] = f"{t[tier]['maker_bp']:g}"
                for c in ("spread", "adverse", "inventory", "hold", "liquidation"):
                    V[f"{v}_{tier}_{c}_sig{sig}"] = S.ci(t[tier][c])
                V[f"{v}_{tier}_gap"] = f"{t[tier]['identity_gap_usd']:.1e}"
            for h in (1, 10, 60):
                V[f"{v}_mo{h}_sig{sig}"] = S.ci(p["markouts"].get(f"{h}s"))
            reasons = p["reasons"]
            tot = max(sum(reasons.values()), 1)
            V[f"{v}_share_through_cross_sig{sig}"] = f"{100 * (reasons.get('through', 0) + reasons.get('cross', 0)) / tot:.0f}"
            V[f"{v}_share_queue_sig{sig}"] = f"{100 * (reasons.get('queue', 0) + reasons.get('depth', 0) + reasons.get('l3', 0)) / tot:.0f}"
            V[f"{v}_rejected_sig{sig}"] = str(p["stats"]["rejected_post_only"])
            V[f"{v}_placed_sig{sig}"] = f"{p['stats']['placed']:,}"
        V[f"{v}_leader"] = NAME[rp["leader_for"][v]]
        e = rp["signal_effect"].get(v, {})
        for tier in ("entry", "top"):
            V[f"{v}_effect_{tier}"] = S.dci(e.get(tier))
            V[f"{v}_effect_{tier}_word"] = effect_word(e.get(tier))
        V[f"{v}_effect_adverse"] = S.dci(e.get("adverse_60s"))
    # ---- sensitivity: latency and queue model (top tier, own mid)
    for v in VENUES:
        for l in (0, 50, 200):
            p = S.find(passes, v, 0, l, qm, cd)
            V[f"{v}_top_lat{l}"] = S.ci(p["tiers"]["top"]["pnl"]) if p else "—"
        for q in ("naive_fifo", "power_prob", "risk_averse", "l3_exact"):
            p = S.find(passes, v, 0, lat, q, cd)
            V[f"{v}_top_{q}"] = S.ci(p["tiers"]["top"]["pnl"]) if p else "—"
            V[f"{v}_fills_{q}"] = str(p["n_fills"]) if p else "—"
        for c in (0.25, 0.5, 1.0):
            p = S.find(passes, v, 0, lat, qm, c)
            V[f"{v}_top_cd{c:g}"] = S.ci(p["tiers"]["top"]["pnl"]) if p else "—"
            V[f"{v}_fph_cd{c:g}"] = f"{p['fills_per_hour']:.0f}" if p else "—"
    # ---- how much the queue model moves the top-tier answer (own mid, base latency and width)
    parts = []
    for v in VENUES:
        vals = [S.find(passes, v, 0, lat, q, cd) for q in ("naive_fifo", "power_prob", "risk_averse", "l3_exact")]
        vals = [x["tiers"]["top"]["pnl"]["mean"] for x in vals if x]
        if len(vals) >= 2:
            parts.append(f"{max(vals) - min(vals):.2f} bp on {NAME[v]}")
    V["qm_spread_sentence"] = ("the choice of queue-position model moves the top-tier figure by at most " + ", ".join(parts)) if parts else "the queue-model sensitivity was not run"
    # ---- lead-lag
    for r in ll["results"]:
        key = f"ll_{r['x']}_{r['y']}_{r['variant']}"
        V[key + "_theta"] = f"{r['theta_star'] * 1000:.0f} ms [{r['theta_lo'] * 1000:.0f}, {r['theta_hi'] * 1000:.0f}]"
        V[key + "_llr"] = f"{r['llr']:.2f} [{r['llr_lo']:.2f}, {r['llr_hi']:.2f}]"
        V[key + "_rho0"] = f"{r['rho_0']:.2f}"
        V[key + "_rhostar"] = f"{r['rho_star']:.2f}"
        V[key + "_p"] = f"{r['p_x_leads']:.2f}"
        V[key + "_blocks"] = str(r["n_blocks"])
    V["ll_grid_ms"] = str(ll["grid_ms"])
    V["ll_step_ms"] = str(ll["step_ms"])
    V["ll_block_min"] = f"{ll['block_s'] / 60:.0f}"
    V["ll_leaders"] = ", ".join(f"{NAME[v]} is re-marked off {NAME[u]}" for v, u in ll["leader_for"].items())
    for k, b in ll["basis_bp"].items():
        a, c = k.split(" - ")
        V[f"basis_{a}_{c}_mean"] = f"{b['mean_bp']:.1f}"
        V[f"basis_{a}_{c}_sd"] = f"{b['sd_bp']:.1f}"
    # the exchange-clock verdict sentence
    ex = {(r["x"], r["y"]): r for r in ll["results"] if r["variant"] == "exchange"}
    rc = {(r["x"], r["y"]): r for r in ll["results"] if r["variant"] == "receive"}
    def verdict(r):
        a, b = NAME[r["x"]], NAME[r["y"]]
        th = r["theta_star"] * 1000
        llr = f"LLR {r['llr']:.2f} [{r['llr_lo']:.2f}, {r['llr_hi']:.2f}]"
        tstar = f"θ* = {th:+.0f} ms [{r['theta_lo'] * 1000:+.0f}, {r['theta_hi'] * 1000:+.0f}], positive meaning {a} first"
        if r["llr_lo"] > 1:
            return f"{a} leads {b} ({llr}; {tstar})"
        if r["llr_hi"] < 1:
            return f"{b} leads {a} ({llr}; {tstar})"
        return f"{a} and {b} are not separable ({llr}; {tstar})"
    V["ll_verdict_exchange"] = "; ".join(verdict(r) for r in ex.values())
    V["ll_verdict_receive"] = "; ".join(verdict(r) for r in rc.values())
    # ---- tables from the summary renderer
    text = S.render(R)
    def section(title_start):
        lines = text.splitlines()
        out, on = [], False
        for ln in lines:
            if ln.startswith("## ") or ln.startswith("### "):
                on = ln.startswith(title_start)
                continue
            if on and ln.startswith("|"):
                out.append(ln)
        return "\n".join(out)
    V["table_headline"] = section("## P&L per fill")
    V["table_effect"] = section("### Re-marking effect")
    V["table_attribution"] = section("## Attribution")
    V["table_markouts"] = section("## Mark-outs")
    V["table_sensitivity"] = section("## Sensitivity")
    V["table_leadlag"] = section("## Lead-lag")
    V["table_recording"] = section("## Recording")
    # ---- tests
    n_tests = 0
    for p in glob.glob(os.path.join(ROOT, "tests", "test_*.py")):
        with open(p, encoding="utf-8") as fh:
            n_tests += len(re.findall(r"^def test_", fh.read(), flags=re.M))
    V["n_tests"] = str(n_tests)
    V["built_utc"] = rp["built_utc"]
    V["replay_seconds"] = f"{rp['seconds']:.0f}"
    V["n_passes"] = str(len(passes))
    return V


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    V = build_values()
    with open(os.path.join(ROOT, "scripts", "README.template.md"), encoding="utf-8") as fh:
        tpl = fh.read()
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: V.get(m.group(1), m.group(0)), tpl)
    left = sorted(set(re.findall(r"\{\{(\w+)\}\}", out)))
    if left:
        print("unfilled placeholders:", ", ".join(left))
        sys.exit(1)
    if args.check:
        print(f"README renders: {len(out.splitlines())} lines, {len(V)} values")
        return
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    print("wrote README.md")


if __name__ == "__main__":
    main()
