"""Replay of the one-lot quoter on one venue's normalised tables with queue-position fills.

Timeline. Event time is the exchange timestamp of each message. A decision every `decision_ms` at time d uses the
book and the leader's mid as they were at d - L (one-way latency L) and its orders / cancels take effect at d + L.
Fills that happen before a cancel takes effect count. Exchange clocks are taken as synchronised (NTP) and the latency
as symmetric; both are stated limitations.

Fill rules for a resting order of ours at price P on side S (bid S = 0, ask S = 1), size `lot`:
  queue    a trade at P initiated against our side consumes the queue ahead of us under the queue model
           (cvq.vendor.queue_model); once the estimated front is below zero the excess executes against us;
  through  a trade against our side at a price beyond P (a sell below our bid, a buy above our ask) fills us in full:
           the taker swept our level before reaching that print;
  cross    the opposite best moves to or through P (best ask <= our bid): the quotes jumped through the order, and
           the order would have been hit on the way; filled in full at P;
  depth    the level's visible size falls by more than the trades recorded at it and more than the estimated size
           behind us (hftbacktest's rule): the model attributes the excess to executions against us;
  l3_exact Bitstamp only, no model: the orders ahead of us are known by id. A trade at P whose maker order id was
           created after ours (or when nothing is ahead) would have hit us first under FIFO: it fills us.
A post-only order that would cross the book when it arrives is rejected (counted).

Inventory. q in lots; the side that would take |q| beyond max_inventory is not quoted; at the end of each episode
the residual inventory is flattened at the far touch (a taker trade, charged the taker fee in cvq.pnl) and the
quoter starts the next episode flat. Episodes are also the block-bootstrap unit.
"""
from __future__ import annotations

import math
import os
import time

import numpy as np
import pandas as pd

from . import books
from .quoter import TICK, Ewma, EwmaVol, QuoterParams, target_quotes
from .vendor.queue_model import QueueModel

QUEUE_MODELS = ("naive_fifo", "power_prob", "risk_averse", "l3_exact")
NS = 1_000_000_000


class RestingOrder:
    __slots__ = ("side", "price", "pt", "remaining", "t_post", "t_eff", "qpos", "level_qty", "taken", "ahead", "ahead_qty",
                 "ahead_ever", "queue_at_post", "mid_at_post", "sigma_bp", "delta_bp", "cancelling")

    def __init__(self, side, price, remaining, t_post, t_eff, mid_at_post, sigma_bp, delta_bp):
        self.side, self.price, self.pt = side, price, int(round(price / TICK))
        self.remaining, self.t_post, self.t_eff = remaining, t_post, t_eff
        self.qpos = None
        self.level_qty = 0.0
        self.taken = 0.0            # size already executed through the queue model's negative front
        self.ahead = None           # l3_exact: {order_id: amount} ahead of us
        self.ahead_qty = 0.0
        self.ahead_ever = None      # l3_exact: every id that was ahead of us when we joined (the live_orders and
                                    # live_trades channels are not causally ordered: a maker ahead of us can be
                                    # deleted before its trade print arrives, and that print is still not ours)
        self.queue_at_post = 0.0
        self.mid_at_post, self.sigma_bp, self.delta_bp = mid_at_post, sigma_bp, delta_bp
        self.cancelling = False


def _leader_mid_series(derived: str, venue: str) -> tuple[np.ndarray, np.ndarray]:
    bbo = books.load_concat(derived, venue, "bbo")
    if bbo.empty:
        return np.array([], np.int64), np.array([])
    bbo = bbo.sort_values("ts", kind="stable")
    return bbo.ts.to_numpy(np.int64), (0.5 * (bbo.bid + bbo.ask)).to_numpy()


def run(derived: str, venue: str, prm: QuoterParams, queue_model: str = "naive_fifo", leader: str | None = None,
        hours: list[str] | None = None, log=None) -> dict:
    """Replay one configuration. Returns {'fills': DataFrame, 'episodes': DataFrame, 'stats': dict}."""
    if queue_model not in QUEUE_MODELS:
        raise ValueError(queue_model)
    if queue_model == "l3_exact" and venue != "bitstamp":
        raise ValueError("l3_exact needs order ids: Bitstamp only")
    hours = hours if hours is not None else books.hours(derived, venue)
    if not hours:
        raise FileNotFoundError(f"no derived hours for {venue} under {derived}")
    t_start = time.time()
    L = prm.latency_ms * 1_000_000
    step = prm.decision_ms * 1_000_000
    lot = prm.lot
    qm = QueueModel(queue_model if queue_model != "l3_exact" else "naive_fifo")
    exact = queue_model == "l3_exact"

    # the venue's own top of book over the whole session (the delayed view at decisions and the mark-out tape)
    own = books.load_concat(derived, venue, "bbo", hours).sort_values("ts", kind="stable")
    own_ts = own.ts.to_numpy(np.int64)
    own_bid, own_ask = own.bid.to_numpy(), own.ask.to_numpy()
    n_own = len(own_ts)
    if prm.signal:
        lead_ts, lead_mid = _leader_mid_series(derived, leader)
        if len(lead_ts) == 0:
            raise FileNotFoundError(f"no leader bbo for {leader}")
    else:
        lead_ts, lead_mid = np.array([], np.int64), np.array([])

    vol = EwmaVol(prm.vol_halflife_s, prm.sigma0_bp)
    basis = Ewma(prm.basis_halflife_s)
    p_own = -1       # pointer: last own bbo row with ts <= seen time
    p_lead = -1
    inv = 0.0        # BTC
    orders = [None, None]       # resting (effective) orders by side
    pending = []                # (t_eff, kind, payload) in time order
    fills, episodes = [], []
    stats = {"decisions": 0, "placed": 0, "cancelled": 0, "rejected_post_only": 0, "fills": 0,
             "fill_reasons": {"queue": 0, "through": 0, "cross": 0, "depth": 0, "l3": 0}, "msgs": 0, "hours": len(hours)}
    book = ({}, {})             # price_ticks -> qty per side (replayed from the l2 rows)
    oap = {}                    # l3_exact: (side, pt) -> {oid: amount}
    oidx = {}                   # l3_exact: oid -> (side, pt)
    cur_bid = cur_ask = None
    episode_len = int(prm.episode_s * NS)
    episode_end = None
    episode_id = -1
    next_decision = None

    def mid_now():
        return 0.5 * (cur_bid + cur_ask) if cur_bid is not None and cur_ask is not None else None

    def record_fill(o: RestingOrder, qty: float, price: float, t: int, reason: str, mid_ref=None):
        nonlocal inv
        if qty <= 1e-12:
            return
        sgn = 1 if o.side == 0 else -1
        inv += sgn * qty
        o.remaining -= qty
        m = mid_now() if mid_ref is None else mid_ref
        fills.append((t, sgn, price, qty, m if m is not None else np.nan, inv / lot, episode_id, reason, (t - o.t_eff) / NS,
                      o.queue_at_post, o.mid_at_post, o.sigma_bp, o.delta_bp, o.level_qty))
        stats["fills"] += 1
        stats["fill_reasons"][reason] += 1
        if o.remaining <= 1e-12:
            orders[o.side] = None

    def fill_check_queue(o: RestingOrder, t: int):
        ex = QueueModel.executable(o.qpos) - o.taken
        if ex > 1e-12:
            q = min(ex, o.remaining)
            o.taken += q
            record_fill(o, q, o.price, t, "queue")

    def on_trade(t: int, price: float, qty: float, aggressor: int, maker_id: int):
        pt = int(round(price / TICK))
        # a seller-initiated trade (aggressor -1) hits bids; a buyer-initiated one lifts asks
        side = 0 if aggressor < 0 else 1
        o = orders[side]
        if o is None or t < o.t_eff:
            return
        if (side == 0 and pt < o.pt) or (side == 1 and pt > o.pt):
            record_fill(o, o.remaining, o.price, t, "through")
            return
        if pt != o.pt:
            return
        if exact:
            if o.ahead_qty <= 1e-12 or maker_id not in o.ahead_ever:
                record_fill(o, min(qty, o.remaining), o.price, t, "l3")
            return
        qm.trade(o.qpos, qty)
        fill_check_queue(o, t)

    def on_level(side: int, pt: int, qty: float, t: int):
        o = orders[side]
        if o is None or o.pt != pt or t < o.t_eff:
            return
        if exact:
            return
        prev = o.level_qty
        o.level_qty = qty
        qm.depth(o.qpos, prev, qty)
        ex = QueueModel.executable(o.qpos) - o.taken
        if ex > 1e-12:
            q = min(ex, o.remaining)
            o.taken += q
            record_fill(o, q, o.price, t, "depth")

    def on_l3(action: int, side: int, oid: int, pt: int, amount: float, t: int):
        key = (side, pt)
        if action == 3:
            loc = oidx.pop(oid, None)
            if loc is not None:
                d = oap.get(loc)
                if d is not None:
                    d.pop(oid, None)
        else:
            loc = oidx.get(oid)
            if loc is not None and loc != key:
                d = oap.get(loc)
                if d is not None:
                    d.pop(oid, None)
            oidx[oid] = key
            oap.setdefault(key, {})[oid] = amount
        o = orders[side]
        if o is not None and o.ahead is not None and oid in o.ahead and t >= o.t_eff:
            if action == 3 or key != (o.side, o.pt):
                o.ahead_qty -= o.ahead.pop(oid)
            else:
                o.ahead_qty += amount - o.ahead[oid]
                o.ahead[oid] = amount
            if o.ahead_qty < 1e-12:
                o.ahead_qty = 0.0

    def cross_check(t: int, mid_before):
        """The opposite best moved to or through our price: filled in full, marked against the mid before the jump
        (the same convention as a trade printing through us, whose mid is the pre-trade one)."""
        for side in (0, 1):
            o = orders[side]
            if o is None or t < o.t_eff:
                continue
            if (side == 0 and cur_ask is not None and cur_ask <= o.price + 1e-9) or \
               (side == 1 and cur_bid is not None and cur_bid >= o.price - 1e-9):
                record_fill(o, o.remaining, o.price, t, "cross", mid_before)

    def place_effective(t: int, side: int, price: float, mid_at_post, sigma_bp, delta_bp, t_post):
        if cur_bid is None or cur_ask is None:
            return
        if (side == 0 and price >= cur_ask - 1e-9) or (side == 1 and price <= cur_bid + 1e-9):
            stats["rejected_post_only"] += 1
            return
        if orders[side] is not None:
            return  # the previous order has not been cancelled yet (should not happen: cancel precedes place)
        o = RestingOrder(side, price, lot, t_post, t, mid_at_post, sigma_bp, delta_bp)
        level_qty = book[side].get(o.pt, 0.0)
        o.level_qty = level_qty
        o.queue_at_post = level_qty
        o.qpos = qm.new_order(level_qty)
        if exact:
            d = oap.get((side, o.pt), {})
            o.ahead = dict(d)
            o.ahead_ever = set(d.keys())
            o.ahead_qty = sum(d.values())
            o.queue_at_post = o.ahead_qty
        orders[side] = o
        stats["placed"] += 1

    def decide(d: int):
        nonlocal p_own, p_lead
        seen = d - L
        while p_own + 1 < n_own and own_ts[p_own + 1] <= seen:
            p_own += 1
        if p_own < 0:
            return
        bid, ask = own_bid[p_own], own_ask[p_own]
        mid = 0.5 * (bid + ask)
        vol.update(seen / NS, mid)
        m_ref = mid
        if prm.signal:
            while p_lead + 1 < len(lead_ts) and lead_ts[p_lead + 1] <= seen:
                p_lead += 1
            if p_lead >= 0:
                # the leader's mid re-based by the trailing cross-venue difference (on the first decision b is the
                # current difference itself, so m_ref starts at the own mid)
                b = basis.update(seen / NS, lead_mid[p_lead] - mid)
                m_ref = lead_mid[p_lead] - b
        q_lots = inv / lot
        sigma = vol.sigma_bp
        tb, ta, delta, kappa = target_quotes(m_ref, q_lots, sigma, bid, ask, prm)
        stats["decisions"] += 1
        tol = prm.requote_tol_bp * 1e-4 * mid
        for side, target in ((0, tb), (1, ta)):
            o = orders[side]
            has = o is not None and not o.cancelling
            if has:
                stale = (d - o.t_post) >= prm.T * NS
                moved = target is None or abs(target - o.price) > max(tol, TICK * 0.5)
                if stale or moved:
                    o.cancelling = True
                    pending.append((d + L, 0, side))
                    if target is not None:
                        pending.append((d + L, 1, (side, target, mid, sigma, delta, d)))
            elif o is None and target is not None and not any(k == 1 and p[0] == side for _, k, p in pending):
                pending.append((d + L, 1, (side, target, mid, sigma, delta, d)))

    def apply_pending(upto: int):
        nonlocal pending
        while pending and pending[0][0] <= upto:
            t_eff, kind, payload = pending.pop(0)
            if kind == 0:
                o = orders[payload]
                if o is not None:
                    orders[payload] = None
                    stats["cancelled"] += 1
            else:
                side, price, mid_at_post, sigma, delta, t_post = payload
                place_effective(t_eff, side, price, mid_at_post, sigma, delta, t_post)

    def end_episode(t: int):
        nonlocal inv, episode_id, episode_end
        if episode_id >= 0:
            m = mid_now()
            q = inv
            liq_px = (cur_bid if q > 0 else cur_ask) if m is not None else np.nan
            episodes.append((episode_id, episode_end, q / lot, m, cur_bid, cur_ask, liq_px))
            inv = 0.0
            for side in (0, 1):
                orders[side] = None
            pending.clear()
        episode_id += 1
        episode_end = (t // episode_len + 1) * episode_len

    for hour in hours:
        tabs = books.load_hour(derived, venue, hour, ("msgs", "l2", "trades", "bbo") + (("l3",) if exact else ()))
        msgs = tabs["msgs"]
        n = len(msgs)
        if n == 0:
            continue
        m_ts = msgs.ts.to_numpy(np.int64).tolist()
        m_kind = msgs.kind.to_numpy().tolist()
        l2 = tabs["l2"]
        l2_msg = l2.msg.to_numpy(np.int32)
        l2_start = np.searchsorted(l2_msg, np.arange(n + 1), side="left").tolist()
        l2_side, l2_pt, l2_qty = l2.side.to_numpy().tolist(), np.round(l2.price.to_numpy() / TICK).astype(np.int64).tolist(), l2.qty.to_numpy().tolist()
        tr = tabs["trades"]
        tr_by_msg = {}
        for i_m, p, q, a, mk in zip(tr.msg.to_numpy().tolist(), tr.price.to_numpy().tolist(), tr.qty.to_numpy().tolist(),
                                    tr.aggressor.to_numpy().tolist(), tr.maker_order_id.to_numpy().tolist()):
            tr_by_msg.setdefault(i_m, []).append((p, q, a, mk))
        bb = tabs["bbo"]
        bb_by_msg = dict(zip(bb.msg.to_numpy().tolist(), zip(bb.bid.to_numpy().tolist(), bb.ask.to_numpy().tolist())))
        if exact:
            l3 = tabs["l3"]
            l3_msg = l3.msg.to_numpy(np.int32)
            l3_start = np.searchsorted(l3_msg, np.arange(n + 1), side="left").tolist()
            l3_action, l3_side, l3_oid = l3.action.to_numpy().tolist(), l3.side.to_numpy().tolist(), l3.order_id.to_numpy().tolist()
            l3_pt, l3_amt = np.round(l3.price.to_numpy() / TICK).astype(np.int64).tolist(), l3.amount.to_numpy().tolist()
        for i in range(n):
            t = m_ts[i]
            if next_decision is None:
                next_decision = (t // step + 1) * step
                end_episode(t)
            if t >= episode_end:
                apply_pending(t)
                end_episode(t)
            while next_decision <= t:
                apply_pending(next_decision)
                decide(next_decision)
                next_decision += step
            apply_pending(t)
            kind = m_kind[i]
            if kind == 2:
                book[0].clear()
                book[1].clear()
                if exact:
                    oap.clear()
                    oidx.clear()
            if kind != 1:
                a, b = l2_start[i], l2_start[i + 1]
                for j in range(a, b):
                    s, pt, q = l2_side[j], l2_pt[j], l2_qty[j]
                    book[s][pt] = q
                    if kind == 0 and orders[s] is not None:
                        on_level(s, pt, q, t)
                if kind == 2:
                    for s in (0, 1):
                        o = orders[s]
                        if o is not None:
                            o.level_qty = book[s].get(o.pt, 0.0)
                if exact:
                    a, b = l3_start[i], l3_start[i + 1]
                    if kind == 2:
                        for j in range(a, b):
                            key = (l3_side[j], l3_pt[j])
                            oidx[l3_oid[j]] = key
                            oap.setdefault(key, {})[l3_oid[j]] = l3_amt[j]
                    else:
                        for j in range(a, b):
                            on_l3(l3_action[j], l3_side[j], l3_oid[j], l3_pt[j], l3_amt[j], t)
            else:
                for p, q, a_, mk in tr_by_msg.get(i, ()):
                    on_trade(t, p, q, a_, mk)
            bq = bb_by_msg.get(i)
            if bq is not None:
                mid_before = mid_now()
                cur_bid, cur_ask = bq
                if orders[0] is not None or orders[1] is not None:
                    cross_check(t, mid_before if mid_before is not None else mid_now())
            stats["msgs"] += 1
        if log:
            log(f"  {venue} {hour}: fills so far {stats['fills']}, inv {inv / lot:.2f} lots, {time.time() - t_start:.0f} s")
    # close the last episode at the end of the tape
    if m_ts:
        episode_end = m_ts[-1]
        end_episode(m_ts[-1])
    fills_df = pd.DataFrame(fills, columns=["t", "side", "price", "qty", "mid", "inv_after_lots", "episode", "reason", "age_s",
                                            "queue_at_post", "mid_at_post", "sigma_bp", "delta_bp", "level_qty_at_fill"])
    ep_df = pd.DataFrame(episodes, columns=["episode", "t_end", "inv_end_lots", "mid_end", "bid_end", "ask_end", "liq_px"])
    stats["seconds"] = round(time.time() - t_start, 1)
    stats["lot"] = lot
    return {"fills": fills_df, "episodes": ep_df, "stats": stats}
