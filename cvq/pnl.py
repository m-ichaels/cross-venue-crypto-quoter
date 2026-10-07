"""P&L attribution per fill and the block bootstrap over episodes.

For a fill of signed side s (+1 buy, -1 sell), size x, price p, mid m0 at the fill, mid m_h at the mark-out horizon h
(capped at the episode end) and mid m_T at the end of the fill's episode, all in basis points of p:

    spread capture      =  s (m0 - p) / p
    adverse selection   = -s (m_h - m0) / p            the h-second mark-out, sign so that a cost is positive
    inventory cost      = -s (m_T - m_h) / p + liq      carrying the position from h to the episode end, plus the
                                                        fill's share of flattening the episode's residual inventory
                                                        at the far touch (half spread + taker fee)
    fees                =  maker fee of the tier
    P&L per fill        =  spread capture - adverse selection - inventory cost - fees

The four terms sum exactly to the episode's realised P&L: sum over fills of s x (m_T - p), less the flattening cost,
less fees, because m_T - p = (m0 - p) + (m_h - m0) + (m_T - m_h). Reported per-fill numbers are notional-weighted
means (sum of dollar P&L over sum of dollar notional, in bp); intervals come from resampling episodes with replacement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NS = 1_000_000_000
HORIZONS = (1, 10, 60)


def mid_at(bbo_ts: np.ndarray, bbo_mid: np.ndarray, t: np.ndarray, t_max=None) -> np.ndarray:
    """Previous-tick mid at times t (ns); NaN before the first quote and beyond t_max (default: the last quote)."""
    k = np.searchsorted(bbo_ts, t, side="right") - 1
    out = np.where(k >= 0, bbo_mid[np.clip(k, 0, len(bbo_mid) - 1)], np.nan)
    t_max = bbo_ts[-1] if t_max is None else t_max
    out = np.where(t > t_max, np.nan, out)
    return out


def add_markouts(fills: pd.DataFrame, episodes: pd.DataFrame, bbo_ts: np.ndarray, bbo_mid: np.ndarray,
                 horizons=HORIZONS) -> pd.DataFrame:
    f = fills.copy()
    if f.empty:
        for h in horizons:
            f[f"mid_{h}s"] = np.nan
        f["mid_end"] = np.nan
        return f
    ep_end = episodes.set_index("episode")["t_end"]
    t_end = f["episode"].map(ep_end).to_numpy(np.int64)
    t = f["t"].to_numpy(np.int64)
    t_max = int(episodes["t_end"].max())      # the tape ends with the last episode, not with the last quote change
    for h in horizons:
        th = np.minimum(t + h * NS, t_end)
        f[f"mid_{h}s"] = mid_at(bbo_ts, bbo_mid, th, t_max)
    f["mid_end"] = mid_at(bbo_ts, bbo_mid, t_end, t_max)
    for h in horizons:
        f[f"markout_{h}s_bp"] = f["side"] * (f[f"mid_{h}s"] - f["price"]) / f["price"] * 1e4
    return f


def attribute(fills: pd.DataFrame, episodes: pd.DataFrame, maker_bp: float, taker_bp: float, lot: float,
              horizon: int = 60) -> pd.DataFrame:
    """Per-fill attribution in bp of the fill price at one fee tier (see the module docstring)."""
    f = fills.copy()
    if f.empty:
        for c in ("spread_bp", "adverse_bp", "hold_bp", "liq_bp", "inventory_bp", "fee_bp", "pnl_bp", "notional"):
            f[c] = np.nan
        return f
    s, p = f["side"], f["price"]
    m0, mh, mT = f["mid"], f[f"mid_{horizon}s"], f["mid_end"]
    f["spread_bp"] = s * (m0 - p) / p * 1e4
    f["adverse_bp"] = -s * (mh - m0) / p * 1e4
    f["hold_bp"] = -s * (mT - mh) / p * 1e4
    f["notional"] = f["qty"] * p
    # flattening cost per episode, allocated to the episode's fills in proportion to notional
    ep = episodes.set_index("episode")
    inv_btc = ep["inv_end_lots"] * lot
    half = (ep["mid_end"] - ep["liq_px"]).abs().fillna(0.0)
    liq_usd = inv_btc.abs() * (half + taker_bp * 1e-4 * ep["mid_end"].fillna(0.0))
    notional_by_ep = f.groupby("episode")["notional"].sum()
    liq_bp_by_ep = (liq_usd.reindex(notional_by_ep.index).fillna(0.0) / notional_by_ep * 1e4)
    f["liq_bp"] = f["episode"].map(liq_bp_by_ep).fillna(0.0)
    f["inventory_bp"] = f["hold_bp"] + f["liq_bp"]
    f["fee_bp"] = float(maker_bp)
    f["pnl_bp"] = f["spread_bp"] - f["adverse_bp"] - f["inventory_bp"] - f["fee_bp"]
    return f


def weighted_bp(f: pd.DataFrame, col: str) -> float:
    w = f["notional"].to_numpy()
    v = f[col].to_numpy()
    ok = np.isfinite(v)
    return float(np.sum(v[ok] * w[ok]) / np.sum(w[ok])) if ok.any() and np.sum(w[ok]) > 0 else float("nan")


def bootstrap_weighted(f: pd.DataFrame, col: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """Notional-weighted mean of `col` with a 95 % interval from resampling episodes with replacement."""
    ok = f[np.isfinite(f[col])]
    if ok.empty:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n_fills": 0, "n_episodes": 0}
    g = ok.assign(v=ok[col] * ok["notional"]).groupby("episode").agg(v=("v", "sum"), w=("notional", "sum"))
    v, w = g["v"].to_numpy(), g["w"].to_numpy()
    n = len(v)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot = v[idx].sum(1) / w[idx].sum(1)
    return {"mean": float(v.sum() / w.sum()), "lo": float(np.percentile(boot, 2.5)), "hi": float(np.percentile(boot, 97.5)),
            "n_fills": int(len(ok)), "n_episodes": int(n)}


def bootstrap_difference(fa: pd.DataFrame, fb: pd.DataFrame, col: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """Paired (by episode) bootstrap of the difference in the notional-weighted mean of `col`, a minus b."""
    def agg(f):
        ok = f[np.isfinite(f[col])]
        return ok.assign(v=ok[col] * ok["notional"]).groupby("episode").agg(v=("v", "sum"), w=("notional", "sum"))
    ga, gb = agg(fa), agg(fb)
    eps = sorted(set(ga.index) | set(gb.index))
    if not eps:
        return {"diff": float("nan"), "lo": float("nan"), "hi": float("nan"), "n_episodes": 0}
    va, wa = ga.reindex(eps).fillna(0.0)["v"].to_numpy(), ga.reindex(eps).fillna(0.0)["w"].to_numpy()
    vb, wb = gb.reindex(eps).fillna(0.0)["v"].to_numpy(), gb.reindex(eps).fillna(0.0)["w"].to_numpy()
    n = len(eps)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    with np.errstate(invalid="ignore", divide="ignore"):
        boot = va[idx].sum(1) / wa[idx].sum(1) - vb[idx].sum(1) / wb[idx].sum(1)
        d = va.sum() / wa.sum() - vb.sum() / wb.sum()
    boot = boot[np.isfinite(boot)]
    return {"diff": float(d), "lo": float(np.percentile(boot, 2.5)) if len(boot) else float("nan"),
            "hi": float(np.percentile(boot, 97.5)) if len(boot) else float("nan"), "n_episodes": int(n)}


def episode_pnl_check(f: pd.DataFrame, episodes: pd.DataFrame, lot: float, taker_bp: float) -> float:
    """Max absolute gap (USD) between the sum of the attributed per-fill P&L and the episode's realised P&L
    (positions marked at the episode-end mid, flattened at the far touch with the taker fee, maker fees paid)."""
    if f.empty:
        return 0.0
    attributed = (f["pnl_bp"] * f["notional"] / 1e4).groupby(f["episode"]).sum()
    ep = episodes.set_index("episode")
    realised = (f["side"] * f["qty"] * (f["mid_end"] - f["price"]) - f["fee_bp"] * 1e-4 * f["notional"]).groupby(f["episode"]).sum()
    inv_btc = ep["inv_end_lots"] * lot
    liq = inv_btc.abs() * ((ep["mid_end"] - ep["liq_px"]).abs().fillna(0.0) + taker_bp * 1e-4 * ep["mid_end"].fillna(0.0))
    realised = realised - liq.reindex(realised.index).fillna(0.0)
    return float((attributed - realised).abs().max())
