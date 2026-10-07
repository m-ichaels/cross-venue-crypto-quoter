"""The one-lot inventory-skewed passive quoter: Avellaneda-Stoikov / GLFT in its stationary form.

Reservation price and half-spread (Avellaneda & Stoikov 2008; Gueant, Lehalle & Fernandez-Tapia 2013 for the
stationary limit) are taken in basis points of the mid with the risk term written through the mid's short-horizon
volatility rather than through (gamma, k), which this one session cannot identify:

    r_t      = m_ref,t * (1 - q_t * kappa_t / 1e4)              reservation price, skewed against the inventory
    kappa_t  = c_q * sigma_t * sqrt(T)                           skew per lot (bp)
    delta_t  = max(c_delta * sigma_t * sqrt(T), own half spread, 1 tick)   half spread (bp)
    bid_t    = floor_tick(r_t * (1 - delta_t / 1e4)),  ask_t = ceil_tick(r_t * (1 + delta_t / 1e4))

with sigma_t the EWMA volatility of the 1-second log-mid change (bp / sqrt(s)) and T the stale-quote horizon (s):
an order is pulled and re-quoted after T seconds, or when its price is more than `requote_tol` from the new target.
Quotes are post-only: a bid is capped at best ask - 1 tick and an ask floored at best bid + 1 tick. The side that
would take |q| beyond `max_inventory` lots is not quoted.

m_ref is the venue's own mid (signal off) or the leading venue's mid re-based by the EWMA of the cross-venue mid
difference (signal on): m_ref = m_lead - b_t, b_t = EWMA(m_lead - m_own), half-life `basis_halflife_s`.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

TICK = 0.01


@dataclass
class QuoterParams:
    lot: float = 0.01                 # BTC per order ("one lot")
    c_delta: float = 0.5              # half spread = c_delta * sigma * sqrt(T)   (bp)
    c_q: float = 0.25                 # skew per lot = c_q * sigma * sqrt(T)       (bp)
    T: float = 10.0                   # stale-quote horizon (s): quotes older than T are pulled and re-quoted
    requote_tol_bp: float = 0.25      # re-quote when the target moved by more than this (bp) from the resting price
    max_inventory: int = 5            # lots
    decision_ms: int = 100            # decision clock
    vol_halflife_s: float = 120.0     # EWMA half-life of the 1 s squared mid change
    sigma0_bp: float = 0.5            # starting volatility (bp / sqrt(s))
    basis_halflife_s: float = 600.0   # EWMA half-life of the cross-venue mid difference
    episode_s: float = 900.0          # inventory is flattened at the far touch at the end of each episode
    signal: int = 0                   # 0: own mid, 1: re-mark off the leading venue
    latency_ms: int = 50              # one-way latency: data seen late by this, orders effective late by this

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1)


class EwmaVol:
    """EWMA of squared log-mid changes sampled once a second; sigma in bp / sqrt(s)."""

    def __init__(self, halflife_s: float, sigma0_bp: float):
        self.alpha = 1.0 - math.exp(-math.log(2.0) / halflife_s)
        self.var = (sigma0_bp * 1e-4) ** 2
        self.last_t = None
        self.last_m = None

    def update(self, t_s: float, mid: float) -> None:
        if self.last_t is None:
            self.last_t, self.last_m = t_s, mid
            return
        dt = t_s - self.last_t
        if dt >= 1.0:
            r = math.log(mid / self.last_m)
            self.var = (1 - self.alpha) * self.var + self.alpha * r * r / dt
            self.last_t, self.last_m = t_s, mid

    @property
    def sigma_bp(self) -> float:
        return math.sqrt(max(self.var, 1e-16)) * 1e4


class Ewma:
    def __init__(self, halflife_s: float):
        self.lmbda = math.log(2.0) / halflife_s
        self.v = None
        self.last_t = None

    def update(self, t_s: float, x: float) -> float:
        if self.v is None:
            self.v, self.last_t = x, t_s
        else:
            a = 1.0 - math.exp(-self.lmbda * max(t_s - self.last_t, 0.0))
            self.v = (1 - a) * self.v + a * x
            self.last_t = t_s
        return self.v


def floor_tick(p: float) -> float:
    return math.floor(p / TICK + 1e-9) * TICK


def ceil_tick(p: float) -> float:
    return math.ceil(p / TICK - 1e-9) * TICK


def target_quotes(m_ref: float, q_lots: int, sigma_bp: float, best_bid: float, best_ask: float, prm: QuoterParams):
    """Desired (bid, ask) prices, or None on a side that must not be quoted. Pure function for the tests."""
    root_t = math.sqrt(prm.T)
    kappa = prm.c_q * sigma_bp * root_t
    own_half_bp = 0.5 * (best_ask - best_bid) / (0.5 * (best_ask + best_bid)) * 1e4
    delta = max(prm.c_delta * sigma_bp * root_t, own_half_bp, TICK / m_ref * 1e4)
    r = m_ref * (1.0 - q_lots * kappa / 1e4)
    bid = floor_tick(r * (1.0 - delta / 1e4))
    ask = ceil_tick(r * (1.0 + delta / 1e4))
    bid = min(bid, best_ask - TICK)      # post-only
    ask = max(ask, best_bid + TICK)
    if q_lots >= prm.max_inventory:
        bid = None
    if q_lots <= -prm.max_inventory:
        ask = None
    return bid, ask, delta, kappa
