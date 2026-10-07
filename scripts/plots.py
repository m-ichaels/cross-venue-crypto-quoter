#!/usr/bin/env python3
"""Figures from the results files -> figures/*.png.

    python scripts/plots.py [--derived data/derived]   (the session figure needs the derived bbo tables; skipped if absent)

Palette: one fixed hue per venue (Binance blue, Coinbase orange, Bitstamp aqua; validated for colour-vision deficiency
with the dataviz palette checker), the re-marked variant hatched; text in text tokens; hairline grid.
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
FIG = os.path.join(ROOT, "figures")
sys.path.insert(0, ROOT)

VENUES = ("binance", "coinbase", "bitstamp")
NAME = {"binance": "Binance", "coinbase": "Coinbase", "bitstamp": "Bitstamp"}
COLOR = {"binance": "#2a78d6", "coinbase": "#eb6834", "bitstamp": "#1baf7a"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 1.0, "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
                     "axes.titlesize": 10, "legend.frameon": False, "savefig.dpi": 150})


def load(name):
    with open(os.path.join(RES, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def find(passes, venue, signal, latency, qm, cd):
    for p in passes:
        if p["venue"] == venue and p["signal"] == signal and p["latency_ms"] == latency and p["queue_model"] == qm and abs(p["c_delta"] - cd) < 1e-9:
            return p
    return None


def base(rp):
    return rp["params"]["latency_ms"], rp["base_queue_model"], rp["params"]["c_delta"]


def errbar(ax, x, b, color, hatch=None, width=0.3, label=None):
    if not b or not np.isfinite(b.get("mean", np.nan)):
        return
    ax.bar(x, b["mean"], width=width, color=color if not hatch else SURFACE, edgecolor=color, linewidth=1.2, hatch=hatch, label=label, zorder=3)
    ax.errorbar(x, b["mean"], yerr=[[b["mean"] - b["lo"]], [b["hi"] - b["mean"]]], color=INK2, linewidth=1.0, capsize=3, zorder=4)


SHORT = {"Regular user / VIP 0": "VIP 0", "$0K-$10K": "< $10K"}


def fig_pnl(rp):
    lat, qm, cd = base(rp)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=False)
    for ax, tier in zip(axes, ("entry", "top")):
        for i, v in enumerate(VENUES):
            for j, sig in enumerate((0, 1)):
                p = find(rp["passes"], v, sig, lat, qm, cd)
                if p is None:
                    continue
                b = p["tiers"][tier]["pnl"]
                x = i + (-0.18 if sig == 0 else 0.18)
                errbar(ax, x, b, COLOR[v], hatch=None if sig == 0 else "////", width=0.32)
                # the value label sits clear of the interval: below its lower end for a loss, above the upper end for a gain
                y, va = (b["lo"], "top") if b["mean"] < 0 else (b["hi"], "bottom")
                ax.annotate(f"{b['mean']:.1f}", (x, y), xytext=(0, -3 if b["mean"] < 0 else 3), textcoords="offset points",
                            ha="center", va=va, fontsize=8, color=INK, zorder=5)
        ax.axhline(0, color=INK2, linewidth=1.0, zorder=2)
        ax.set_xticks(range(len(VENUES)))
        labels = []
        for v in VENUES:
            p = find(rp["passes"], v, 0, lat, qm, cd)
            if p:
                lab = p["tiers"][tier]["label"]
                labels.append(f"{NAME[v]}\n{SHORT.get(lab, lab)} ({p['tiers'][tier]['maker_bp']:g} bp)")
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_title("entry maker tier" if tier == "entry" else "top maker tier")
        ax.set_ylabel("P&L per fill (bp of notional)")
        lo = ax.get_ylim()[0]
        ax.set_ylim(lo * 1.12 if lo < 0 else lo, ax.get_ylim()[1])
    from matplotlib.patches import Patch
    axes[0].legend(handles=[Patch(facecolor=INK2, label="own mid"), Patch(facecolor=SURFACE, edgecolor=INK2, hatch="////", label="re-marked off the leading venue")],
                   loc="lower left", fontsize=8)
    fig.suptitle(f"One-lot passive quoter, P&L per fill with 95 % episode-bootstrap intervals (latency {lat} ms, {qm})", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "pnl_by_tier.png"))
    plt.close(fig)


def fig_attribution(rp):
    lat, qm, cd = base(rp)
    comps = [("spread", "spread capture", 1), ("adverse", "adverse selection (60 s)", -1), ("inventory", "inventory + flattening", -1), ("fee", "maker fee", -1)]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, v in zip(axes, VENUES):
        p = find(rp["passes"], v, 0, lat, qm, cd)
        if p is None:
            continue
        t = p["tiers"]["top"]
        ys = [sgn * t[k]["mean"] for k, _, sgn in comps]
        xs = np.arange(len(comps))
        ax.bar(xs, ys, width=0.5, color=[COLOR[v] if y >= 0 else SURFACE for y in ys], edgecolor=COLOR[v], linewidth=1.2, zorder=3)
        for x, y, (k, _, sgn) in zip(xs, ys, comps):
            lo, hi = sgn * t[k]["lo"], sgn * t[k]["hi"]
            ax.errorbar(x, y, yerr=[[abs(y - min(lo, hi))], [abs(max(lo, hi) - y)]], color=INK2, linewidth=1.0, capsize=3, zorder=4)
        net = t["pnl"]["mean"]
        ax.axhline(net, color=INK, linewidth=1.0, zorder=2)
        ax.text(len(comps) - 0.5, net, f"net {net:+.2f} bp", ha="right", va="bottom", fontsize=8, color=INK)
        ax.axhline(0, color=INK2, linewidth=1.0, zorder=2)
        ax.set_xticks(xs)
        ax.set_xticklabels([c[1] for c in comps], rotation=20, ha="right", fontsize=8)
        ax.set_title(f"{NAME[v]} — {t['label']} tier, maker {t['maker_bp']:g} bp")
    axes[0].set_ylabel("bp of notional per fill (costs shown negative)")
    fig.suptitle("Attribution of the P&L per fill, own-mid quoter, top maker tier", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "attribution.png"))
    plt.close(fig)


def fig_markouts(rp):
    lat, qm, cd = base(rp)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    hs = [1, 10, 60]
    for i, v in enumerate(VENUES):
        for sig in (0, 1):
            p = find(rp["passes"], v, sig, lat, qm, cd)
            if p is None:
                continue
            m = [p["markouts"].get(f"{h}s", {}) for h in hs]
            y = [b.get("mean", np.nan) for b in m]
            lo = [b.get("mean", np.nan) - b.get("lo", np.nan) for b in m]
            hi = [b.get("hi", np.nan) - b.get("mean", np.nan) for b in m]
            x = np.array(hs) * (1.0 + 0.06 * (i - 1)) * (1.0 if sig == 0 else 1.03)
            ax.errorbar(x, y, yerr=[lo, hi], color=COLOR[v], linewidth=2, marker="o" if sig == 0 else "s", markersize=6,
                        markerfacecolor=COLOR[v] if sig == 0 else SURFACE, markeredgewidth=1.5, capsize=3,
                        label=f"{NAME[v]}, {'own mid' if sig == 0 else 're-marked'}", zorder=3)
    ax.set_xscale("log")
    ax.set_xticks(hs)
    ax.set_xticklabels([f"{h} s" for h in hs])
    ax.axhline(0, color=INK2, linewidth=1.0)
    ax.set_xlabel("mark-out horizon")
    ax.set_ylabel("mark-out of the fills (bp; + = in our favour)")
    ax.legend(fontsize=7, ncol=2)
    ax.set_title("Adverse selection of the passive fills by horizon", fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "markouts.png"))
    plt.close(fig)


def fig_sensitivity(rp):
    lat, qm, cd = base(rp)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    # latency
    ax = axes[0]
    lats = sorted({p["latency_ms"] for p in rp["passes"] if p["queue_model"] == qm and abs(p["c_delta"] - cd) < 1e-9})
    for v in VENUES:
        for sig in (0, 1):
            ys, lo, hi = [], [], []
            for l in lats:
                p = find(rp["passes"], v, sig, l, qm, cd)
                b = p["tiers"]["top"]["pnl"] if p else {"mean": np.nan, "lo": np.nan, "hi": np.nan}
                ys.append(b["mean"]); lo.append(b["mean"] - b["lo"]); hi.append(b["hi"] - b["mean"])
            ax.errorbar(np.array(lats) + (3 if sig else -3), ys, yerr=[lo, hi], color=COLOR[v], linewidth=2, marker="o" if sig == 0 else "s",
                        markersize=6, markerfacecolor=COLOR[v] if sig == 0 else SURFACE, capsize=3, label=f"{NAME[v]}, {'own mid' if sig == 0 else 're-marked'}")
    ax.set_xticks(lats)
    ax.set_xlabel("one-way latency (ms)")
    ax.set_ylabel("P&L per fill, top tier (bp)")
    ax.set_title("latency")
    ax.legend(fontsize=7)
    # queue model
    ax = axes[1]
    qms = ["naive_fifo", "power_prob", "risk_averse", "l3_exact"]
    for i, v in enumerate(VENUES):
        for j, q in enumerate(qms):
            p = find(rp["passes"], v, 0, lat, q, cd)
            if p is None:
                continue
            errbar(ax, j + (i - 1) * 0.27, p["tiers"]["top"]["pnl"], COLOR[v], width=0.25)
    ax.set_xticks(range(len(qms)))
    ax.set_xticklabels(qms, fontsize=8)
    ax.set_title("queue-position model (own mid)")
    # half-spread multiplier
    ax = axes[2]
    cds = sorted({p["c_delta"] for p in rp["passes"] if p["latency_ms"] == lat and p["queue_model"] == qm})
    for i, v in enumerate(VENUES):
        for j, c in enumerate(cds):
            p = find(rp["passes"], v, 0, lat, qm, c)
            if p is None:
                continue
            errbar(ax, j + (i - 1) * 0.27, p["tiers"]["top"]["pnl"], COLOR[v], width=0.25)
            ax.text(j + (i - 1) * 0.27, p["tiers"]["top"]["pnl"]["hi"], f"{p['fills_per_hour']:.0f}/h", ha="center", va="bottom", fontsize=6.5, color=INK2)
    ax.set_xticks(range(len(cds)))
    ax.set_xticklabels([f"c_delta {c:g}" for c in cds], fontsize=8)
    ax.set_title("half-spread multiplier (fills per hour above)")
    for ax in axes:
        ax.axhline(0, color=INK2, linewidth=1.0)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "sensitivity.png"))
    plt.close(fig)


def fig_leadlag(ll):
    curves = pd.read_csv(os.path.join(RES, "leadlag_curves.csv"))
    pairs = list(dict.fromkeys(curves.pair))
    fig, axes = plt.subplots(1, len(pairs), figsize=(3.6 * len(pairs), 3.4), sharey=True)
    axes = np.atleast_1d(axes)
    pair_color = {"binance vs coinbase": COLOR["binance"], "binance vs bitstamp": COLOR["bitstamp"], "coinbase vs bitstamp": COLOR["coinbase"]}
    for ax, pair in zip(axes, pairs):
        for variant, ls in (("exchange", "-"), ("receive", (0, (4, 2))), ("bookticker", (0, (1, 2)))):
            c = curves[(curves.pair == pair) & (curves.variant == variant)]
            if c.empty:
                continue
            ax.plot(c.theta_ms, c.rho, color=pair_color.get(pair, INK), linewidth=2, linestyle=ls, label=variant)
            r = next((r for r in ll["results"] if r["pair"] == pair and r["variant"] == variant), None)
            if r and variant == "exchange":
                ax.axvline(r["theta_star"] * 1000, color=INK2, linewidth=1.0)
                ax.text(r["theta_star"] * 1000, ax.get_ylim()[1] if False else c.rho.max(), f"  θ* {r['theta_star'] * 1000:.0f} ms, LLR {r['llr']:.2f}",
                        fontsize=8, va="bottom", ha="left", color=INK)
        ax.axvline(0, color=GRID, linewidth=1.0)
        a, b = pair.split(" vs ")
        ax.set_title(f"{NAME[a]} vs {NAME[b]}   (θ > 0: {NAME[a]} leads)")
        ax.set_xlabel("shift θ (ms)")
    axes[0].set_ylabel("Hayashi–Yoshida contrast ρ(θ)")
    axes[0].legend(fontsize=8, title="clock", title_fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "leadlag.png"))
    plt.close(fig)


def fig_session(derived):
    from cvq import books
    if not all(books.hours(derived, v) for v in VENUES):
        return False
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    series = {}
    for v in VENUES:
        bbo = books.load_concat(derived, v, "bbo").sort_values("ts")
        series[v] = (bbo.ts.to_numpy(np.int64), (0.5 * (bbo.bid + bbo.ask)).to_numpy())
    t_lo = max(s[0][0] for s in series.values())
    t_hi = min(s[0][-1] for s in series.values())
    g = np.arange(t_lo, t_hi, 10**9, dtype=np.int64)
    mids = {}
    for v, (t, m) in series.items():
        k = np.clip(np.searchsorted(t, g, side="right") - 1, 0, len(m) - 1)
        mids[v] = m[k]
    hours = (g - g[0]) / 3.6e12
    for v in VENUES:
        axes[0].plot(hours, mids[v], color=COLOR[v], linewidth=1.2, label=NAME[v])
    axes[0].set_ylabel("mid (quote currency)")
    axes[0].legend(fontsize=8)
    axes[0].set_title("The three mids over the recording (1-second previous-tick samples)", fontsize=10)
    for v in ("coinbase", "bitstamp"):
        axes[1].plot(hours, (mids[v] - mids["binance"]) / mids["binance"] * 1e4, color=COLOR[v], linewidth=1.0, label=f"{NAME[v]} − Binance")
    axes[1].axhline(0, color=INK2, linewidth=1.0)
    axes[1].set_ylabel("basis to Binance (bp)")
    axes[1].set_xlabel("hours since the start of the common window")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "session.png"))
    plt.close(fig)
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--derived", default=os.path.join(ROOT, "data", "derived"))
    args = ap.parse_args(argv)
    os.makedirs(FIG, exist_ok=True)
    rp, ll = load("replay"), load("leadlag")
    fig_pnl(rp)
    fig_attribution(rp)
    fig_markouts(rp)
    fig_sensitivity(rp)
    fig_leadlag(ll)
    ok = fig_session(args.derived)
    print("figures written" + ("" if ok else " (session figure skipped: no derived bbo tables)"))


if __name__ == "__main__":
    main()
