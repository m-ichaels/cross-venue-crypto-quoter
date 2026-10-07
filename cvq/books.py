"""Rebuild the three books from the raw recordings and write hourly normalised tables.

Per venue and hour file <venue>/<YYYY-MM-DD>/<HH>.jsonl.gz the builder writes data/derived/<venue>/<YYYY-MM-DDTHH>_*.parquet:

  msgs    one row per applied message:  ts (exchange time, ns), rx (receive time, ns), seq, kind
          kind 0 = depth update, 1 = trade, 2 = reset (a (re)synchronisation: the l2 / l3 rows attached to it are the
          FULL book, so a reader can start from any hour file without a checkpoint)
  l2      level changes:  msg (row index into msgs), side (0 bid / 1 ask), price, qty (absolute size after the change)
  trades  ts, rx, price, qty, aggressor (+1 buyer-initiated / -1 seller-initiated), trade_id, maker_order_id, msg
  bbo     ts, rx, bid, ask, bid_qty, ask_qty, msg  (one row per message after which the top of book changed)
  l3      Bitstamp only: msg, action (1 create / 2 change / 3 delete), side, order_id, price, amount (remaining)

Venue rules
  Binance   depth@100ms diffs synchronised to the REST snapshot with the documented U/u rule: drop events with
            u <= lastUpdateId, the first applied event must satisfy U <= lastUpdateId + 1 <= u, then U == prev u + 1;
            a gap invalidates the book until the next snapshot in the stream (the recorder fetched one on every gap).
            ts = E (event time, ms); trades: ts = T, aggressor = -1 if the buyer was the maker (m) else +1.
  Coinbase  level2_batch: `snapshot` resets, `l2update` carries absolute sizes (0 removes). `match.side` is the MAKER
            side, so side == "sell" is a buyer-initiated trade (+1). ts = the message `time`.
  Bitstamp  live_orders / live_trades (order by order). Events before the REST order_book?group=2 snapshot are buffered;
            the snapshot seeds the order map and buffered events newer than its microtimestamp are replayed onto it.
            L2 is the per-price aggregate of the L3 book. Trade aggressor: the order with the larger id was created
            later and is the taker; `type` (0 buy / 1 sell) is checked against that and disagreements are counted.
  binance_bbo  bookTicker: bbo rows only, ts = rx (the stream has no event time).

All prices are on a $0.01 grid on the three venues; they are kept as float64 and compared through integer ticks.
"""
from __future__ import annotations

import heapq
import json
import os
from array import array
from datetime import datetime, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import raw

TICK = 0.01
VENUES = ("binance", "coinbase", "bitstamp")
BBO_VENUES = ("binance_bbo",)


def to_ticks(p) -> int:
    return int(round(float(p) / TICK))


def iso_ns(s: str) -> int:
    """Coinbase ISO-8601 time with microseconds and a trailing Z, to ns since the epoch."""
    dt = datetime.strptime(s[:26].rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f") if "." in s else datetime.strptime(s.rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1e6) * 1000


# ----------------------------------------------------------------------------------------------
class SideBook:
    """Price (int ticks) -> qty, with a lazily-cleaned heap for the best price."""

    def __init__(self, is_bid: bool):
        self.is_bid = is_bid
        self.q = {}
        self.heap = []
        self.sign = -1 if is_bid else 1  # heapq is a min-heap: bids are stored negated

    def clear(self):
        self.q.clear()
        self.heap.clear()

    def set(self, p: int, qty: float):
        if qty <= 0:
            self.q.pop(p, None)
        else:
            if p not in self.q:
                heapq.heappush(self.heap, self.sign * p)
            self.q[p] = qty

    def best(self):
        """(price_ticks, qty) or (None, 0.0)."""
        h = self.heap
        while h:
            p = self.sign * h[0]
            qty = self.q.get(p)
            if qty is not None:
                return p, qty
            heapq.heappop(h)
        return None, 0.0

    def items(self):
        return self.q.items()


class L2Book:
    def __init__(self):
        self.bids = SideBook(True)
        self.asks = SideBook(False)

    def clear(self):
        self.bids.clear()
        self.asks.clear()

    def side(self, s: int) -> SideBook:
        return self.bids if s == 0 else self.asks

    def bbo(self):
        bp, bq = self.bids.best()
        ap, aq = self.asks.best()
        return bp, bq, ap, aq


# ----------------------------------------------------------------------------------------------
class HourWriter:
    """Accumulates the hourly tables in compact arrays and writes them as parquet."""

    def __init__(self, out_dir: str, venue: str, hour: str, with_l3: bool = False):
        self.out_dir, self.venue, self.hour = out_dir, venue, hour
        self.m_ts, self.m_rx, self.m_seq, self.m_kind = array("q"), array("q"), array("q"), array("b")
        self.l_msg, self.l_side, self.l_price, self.l_qty = array("i"), array("b"), array("d"), array("d")
        self.t_ts, self.t_rx, self.t_price, self.t_qty, self.t_agg, self.t_id, self.t_maker, self.t_msg = \
            array("q"), array("q"), array("d"), array("d"), array("b"), array("q"), array("q"), array("i")
        self.b_ts, self.b_rx, self.b_bid, self.b_ask, self.b_bq, self.b_aq, self.b_msg = \
            array("q"), array("q"), array("d"), array("d"), array("d"), array("d"), array("i")
        self.with_l3 = with_l3
        if with_l3:
            self.o_msg, self.o_action, self.o_side, self.o_id, self.o_price, self.o_amount = \
                array("i"), array("b"), array("b"), array("q"), array("d"), array("d")
        self.last_bbo = None

    def msg(self, ts: int, rx: int, seq: int, kind: int) -> int:
        self.m_ts.append(ts); self.m_rx.append(rx); self.m_seq.append(seq); self.m_kind.append(kind)
        return len(self.m_ts) - 1

    def l2(self, msg: int, side: int, price_ticks: int, qty: float):
        self.l_msg.append(msg); self.l_side.append(side); self.l_price.append(price_ticks * TICK); self.l_qty.append(qty)

    def trade(self, msg: int, ts: int, rx: int, price_ticks: int, qty: float, agg: int, tid: int, maker: int):
        self.t_ts.append(ts); self.t_rx.append(rx); self.t_price.append(price_ticks * TICK); self.t_qty.append(qty)
        self.t_agg.append(agg); self.t_id.append(tid); self.t_maker.append(maker); self.t_msg.append(msg)

    def l3(self, msg: int, action: int, side: int, oid: int, price_ticks: int, amount: float):
        self.o_msg.append(msg); self.o_action.append(action); self.o_side.append(side); self.o_id.append(oid)
        self.o_price.append(price_ticks * TICK); self.o_amount.append(amount)

    def bbo_if_changed(self, msg: int, ts: int, rx: int, book: L2Book, stats: dict) -> None:
        bp, bq, ap, aq = book.bbo()
        if bp is None or ap is None:
            stats["empty_side"] = stats.get("empty_side", 0) + 1
            return
        if bp >= ap:
            stats["crossed"] = stats.get("crossed", 0) + 1
            return
        cur = (bp, bq, ap, aq)
        if cur != self.last_bbo:
            self.last_bbo = cur
            self.b_ts.append(ts); self.b_rx.append(rx); self.b_bid.append(bp * TICK); self.b_ask.append(ap * TICK)
            self.b_bq.append(bq); self.b_aq.append(aq); self.b_msg.append(msg)

    def bbo_raw(self, msg: int, ts: int, rx: int, bid: float, ask: float, bq: float, aq: float):
        cur = (bid, bq, ask, aq)
        if cur != self.last_bbo:
            self.last_bbo = cur
            self.b_ts.append(ts); self.b_rx.append(rx); self.b_bid.append(bid); self.b_ask.append(ask)
            self.b_bq.append(bq); self.b_aq.append(aq); self.b_msg.append(msg)

    def n_msgs(self) -> int:
        return len(self.m_ts)

    def write(self) -> dict:
        d = os.path.join(self.out_dir, self.venue)
        os.makedirs(d, exist_ok=True)
        base = os.path.join(d, self.hour)
        tables = {
            "msgs": pa.table({"ts": np.frombuffer(self.m_ts, np.int64), "rx": np.frombuffer(self.m_rx, np.int64),
                              "seq": np.frombuffer(self.m_seq, np.int64), "kind": np.frombuffer(self.m_kind, np.int8)}),
            "l2": pa.table({"msg": np.frombuffer(self.l_msg, np.int32), "side": np.frombuffer(self.l_side, np.int8),
                            "price": np.frombuffer(self.l_price, np.float64), "qty": np.frombuffer(self.l_qty, np.float64)}),
            "trades": pa.table({"ts": np.frombuffer(self.t_ts, np.int64), "rx": np.frombuffer(self.t_rx, np.int64),
                                "price": np.frombuffer(self.t_price, np.float64), "qty": np.frombuffer(self.t_qty, np.float64),
                                "aggressor": np.frombuffer(self.t_agg, np.int8), "trade_id": np.frombuffer(self.t_id, np.int64),
                                "maker_order_id": np.frombuffer(self.t_maker, np.int64), "msg": np.frombuffer(self.t_msg, np.int32)}),
            "bbo": pa.table({"ts": np.frombuffer(self.b_ts, np.int64), "rx": np.frombuffer(self.b_rx, np.int64),
                             "bid": np.frombuffer(self.b_bid, np.float64), "ask": np.frombuffer(self.b_ask, np.float64),
                             "bid_qty": np.frombuffer(self.b_bq, np.float64), "ask_qty": np.frombuffer(self.b_aq, np.float64),
                             "msg": np.frombuffer(self.b_msg, np.int32)}),
        }
        if self.with_l3:
            tables["l3"] = pa.table({"msg": np.frombuffer(self.o_msg, np.int32), "action": np.frombuffer(self.o_action, np.int8),
                                     "side": np.frombuffer(self.o_side, np.int8), "order_id": np.frombuffer(self.o_id, np.int64),
                                     "price": np.frombuffer(self.o_price, np.float64), "amount": np.frombuffer(self.o_amount, np.float64)})
        sizes = {}
        for name, t in tables.items():
            p = f"{base}_{name}.parquet"
            pq.write_table(t, p, compression="zstd")
            sizes[name] = t.num_rows
        return sizes


def _write_reset(w: HourWriter, book: L2Book, ts: int, rx: int, seq: int, stats: dict) -> int:
    """A kind-2 message carrying the full book, followed by the top of book it implies."""
    m = w.msg(ts, rx, seq, 2)
    for s, sb in ((0, book.bids), (1, book.asks)):
        for p, q in sb.items():
            w.l2(m, s, p, q)
    w.bbo_if_changed(m, ts, rx, book, stats)
    return m


# ----------------------------------------------------------------------------------------------
# Binance
# ----------------------------------------------------------------------------------------------
class BinanceBuilder:
    venue = "binance"

    def __init__(self):
        self.book = L2Book()
        self.synced = False
        self.last_u = None
        self.snapshot = None      # (lastUpdateId, msg dict) awaiting the first matching event
        self.buffer = []          # depth events received before the snapshot, applied after it
        self.stats = {"depth": 0, "trades": 0, "gaps": 0, "resyncs": 0, "dropped_pre_sync": 0}
        self.pending_reset = False

    def _apply(self, ev, w: HourWriter, rx: int):
        ts = int(ev["E"]) * 1_000_000
        m = w.msg(ts, rx, int(ev["u"]), 0)
        for s, key in ((0, "b"), (1, "a")):
            sb = self.book.side(s)
            for p, q in ev[key]:
                pt = to_ticks(p)
                qty = float(q)
                sb.set(pt, qty)
                w.l2(m, s, pt, qty)
        self.last_u = int(ev["u"])
        w.bbo_if_changed(m, ts, rx, self.book, self.stats)
        self.stats["depth"] += 1

    def _try_sync(self, w: HourWriter, rx: int):
        """Snapshot in hand: drop stale buffered events, apply the rest if the chain is intact."""
        L, snap = self.snapshot
        buf = [e for e in self.buffer if int(e["u"]) > L]
        if not buf:
            self.buffer = []
            return
        first = buf[0]
        if not (int(first["U"]) <= L + 1 <= int(first["u"])):
            # snapshot too old for the stream we have: the recorder fetched another one, wait for it
            self.stats["dropped_pre_sync"] += len(self.buffer)
            self.buffer = buf
            self.snapshot = None
            return
        self.book.clear()
        for p, q in snap["bids"]:
            self.book.bids.set(to_ticks(p), float(q))
        for p, q in snap["asks"]:
            self.book.asks.set(to_ticks(p), float(q))
        self.last_u = L
        ts0 = int(first["E"]) * 1_000_000
        _write_reset(w, self.book, ts0, rx, L, self.stats)
        self.synced = True
        self.stats["resyncs"] += 1
        self.snapshot = None
        self.buffer = []
        # the first event may start before L + 1 (it only has to span it); the chain rule applies from the second on
        self.last_u = int(first["U"]) - 1
        for e in buf:
            if int(e["U"]) != self.last_u + 1:
                self.stats["gaps"] += 1
                self.synced = False
                self.buffer = [e]
                return
            self._apply(e, w, rx)

    def feed(self, rec: dict, w: HourWriter):
        kind = rec["kind"]
        rx = int(rec["rx"])
        msg = rec["msg"]
        if kind == "snapshot":
            self.snapshot = (int(msg["lastUpdateId"]), msg)
            self._try_sync(w, rx)
            return
        if kind != "ws":
            return
        stream = msg.get("stream", "")
        data = msg.get("data", {})
        if stream.endswith("@trade"):
            ts = int(data["T"]) * 1_000_000
            m = w.msg(ts, rx, int(data["t"]), 1)
            agg = -1 if data["m"] else 1
            w.trade(m, ts, rx, to_ticks(data["p"]), float(data["q"]), agg, int(data["t"]), -1)
            self.stats["trades"] += 1
            return
        if not stream.endswith("@depth@100ms"):
            return
        if self.synced:
            if int(data["U"]) != self.last_u + 1:
                self.stats["gaps"] += 1
                self.synced = False
                self.buffer = [data]
                return
            self._apply(data, w, rx)
        else:
            self.buffer.append(data)
            if self.snapshot is not None:
                self._try_sync(w, rx)

    def carry(self, w: HourWriter, ts: int, rx: int):
        """Start a new hour file with the full book so each file is self-contained."""
        if self.synced:
            _write_reset(w, self.book, ts, rx, self.last_u, self.stats)


# ----------------------------------------------------------------------------------------------
# Coinbase
# ----------------------------------------------------------------------------------------------
class CoinbaseBuilder:
    venue = "coinbase"

    def __init__(self):
        self.book = L2Book()
        self.synced = False
        self.stats = {"depth": 0, "trades": 0, "resyncs": 0, "gaps": 0, "updates_pre_snapshot": 0}
        self.last_tid = None
        self.last_ts = 0

    def feed(self, rec: dict, w: HourWriter):
        kind = rec["kind"]
        rx = int(rec["rx"])
        msg = rec["msg"]
        if kind == "snapshot":
            self.book.clear()
            for p, q in msg["bids"]:
                self.book.bids.set(to_ticks(p), float(q))
            for p, q in msg["asks"]:
                self.book.asks.set(to_ticks(p), float(q))
            ts = iso_ns(msg["time"]) if "time" in msg else (self.last_ts or rx)
            _write_reset(w, self.book, ts, rx, int(msg.get("sequence", 0) or 0), self.stats)
            self.synced = True
            self.stats["resyncs"] += 1
            return
        if kind != "ws":
            return
        t = msg.get("type")
        if t == "l2update":
            if not self.synced:
                self.stats["updates_pre_snapshot"] += 1
                return
            ts = iso_ns(msg["time"]) if "time" in msg else rx
            self.last_ts = ts
            m = w.msg(ts, rx, 0, 0)
            for side, p, q in msg["changes"]:
                s = 0 if side == "buy" else 1
                pt = to_ticks(p)
                qty = float(q)
                self.book.side(s).set(pt, qty)
                w.l2(m, s, pt, qty)
            w.bbo_if_changed(m, ts, rx, self.book, self.stats)
            self.stats["depth"] += 1
        elif t == "match" or t == "last_match":
            ts = iso_ns(msg["time"])
            tid = int(msg["trade_id"])
            if t == "match" and self.last_tid is not None and tid > self.last_tid + 1:
                self.stats["gaps"] += 1
            self.last_tid = tid
            if t == "last_match":
                return
            m = w.msg(ts, rx, int(msg.get("sequence", 0) or 0), 1)
            agg = 1 if msg["side"] == "sell" else -1   # side is the maker's side
            w.trade(m, ts, rx, to_ticks(msg["price"]), float(msg["size"]), agg, tid, -1)
            self.stats["trades"] += 1

    def carry(self, w: HourWriter, ts: int, rx: int):
        if self.synced:
            _write_reset(w, self.book, ts, rx, 0, self.stats)


# ----------------------------------------------------------------------------------------------
# Bitstamp (order by order)
# ----------------------------------------------------------------------------------------------
class BitstampBuilder:
    venue = "bitstamp"

    def __init__(self):
        self.orders = {}          # id -> (side, price_ticks, amount)
        self.book = L2Book()      # per-price aggregates of the order map
        self.counts = ({}, {})    # per side: price_ticks -> number of resting orders
        self.synced = False
        self.buffer = []          # (rx, msg) before the snapshot
        self.stats = {"orders": 0, "trades": 0, "resyncs": 0, "unknown_delete": 0, "unknown_change": 0,
                      "type_disagree": 0, "snapshot_orders": 0, "reconnects": 0}

    # -- order map ---------------------------------------------------------------------------
    # Level sizes are sums of order amounts; a float subtraction leaves residues like 1e-18 that would keep a dead
    # level alive (and the book crossed), so levels carry an order count and are removed when it reaches zero, and
    # sizes are rounded to the 1e-8 amount grid.
    def _level_sub(self, side: int, pt: int, amount: float, touched: set):
        sb = self.book.side(side)
        cnt = self.counts[side].get(pt, 0) - 1
        if cnt <= 0:
            self.counts[side].pop(pt, None)
            sb.set(pt, 0.0)
        else:
            self.counts[side][pt] = cnt
            sb.set(pt, round(max(sb.q.get(pt, 0.0) - amount, 0.0), 8))
        touched.add((side, pt))

    def _level_add(self, side: int, pt: int, amount: float, touched: set):
        sb = self.book.side(side)
        self.counts[side][pt] = self.counts[side].get(pt, 0) + 1
        sb.set(pt, round(sb.q.get(pt, 0.0) + amount, 8))
        touched.add((side, pt))

    def _set_order(self, oid: int, side: int, pt: int, amount: float, touched: set):
        old = self.orders.get(oid)
        if old is not None:
            os_, op, oa = old
            self._level_sub(os_, op, oa, touched)
        if amount > 0:
            self.orders[oid] = (side, pt, amount)
            self._level_add(side, pt, amount, touched)
        elif old is not None:
            del self.orders[oid]

    def _del_order(self, oid: int, touched: set) -> bool:
        old = self.orders.pop(oid, None)
        if old is None:
            return False
        os_, op, oa = old
        self._level_sub(os_, op, oa, touched)
        return True

    def _emit_levels(self, w: HourWriter, m: int, touched: set):
        for s, p in touched:
            w.l2(m, s, p, self.book.side(s).q.get(p, 0.0))

    def _load_snapshot(self, msg: dict, w: HourWriter, rx: int):
        self.orders.clear()
        self.book.clear()
        self.counts[0].clear()
        self.counts[1].clear()
        for s, key in ((0, "bids"), (1, "asks")):
            for row in msg[key]:
                p, a, oid = row[0], row[1], int(row[2])
                pt, amount = to_ticks(p), float(a)
                if oid in self.orders:   # same order listed twice: keep one
                    continue
                self.orders[oid] = (s, pt, amount)
                self._level_add(s, pt, amount, set())
        snap_us = int(msg["microtimestamp"])
        ts = snap_us * 1000
        m = w.msg(ts, rx, snap_us, 2)
        for s, sb in ((0, self.book.bids), (1, self.book.asks)):
            for p, q in sb.items():
                w.l2(m, s, p, q)
        for oid, (s, pt, a) in self.orders.items():
            w.l3(m, 1, s, oid, pt, a)
        w.bbo_if_changed(m, ts, rx, self.book, self.stats)
        self.stats["snapshot_orders"] += len(self.orders)
        self.stats["resyncs"] += 1
        self.synced = True
        # replay the buffered stream events that are newer than the snapshot
        buf = self.buffer
        self.buffer = []
        for brx, bmsg in buf:
            d = bmsg.get("data") or {}
            mt = d.get("microtimestamp")
            if mt is None or int(mt) <= snap_us:
                continue
            self._apply_ws(bmsg, w, brx)

    def _apply_ws(self, msg: dict, w: HourWriter, rx: int):
        ev = msg.get("event")
        d = msg.get("data") or {}
        if ev in ("order_created", "order_changed", "order_deleted"):
            ts = int(d["microtimestamp"]) * 1000
            oid = int(d["id"])
            side = int(d["order_type"])          # 0 buy, 1 sell
            pt = to_ticks(d["price_str"] if "price_str" in d else d["price"])
            amount = float(d["amount_str"] if "amount_str" in d else d["amount"])
            m = w.msg(ts, rx, oid, 0)
            touched = set()
            if ev == "order_deleted":
                if not self._del_order(oid, touched):
                    self.stats["unknown_delete"] += 1
                w.l3(m, 3, side, oid, pt, 0.0)
            else:
                if ev == "order_changed" and oid not in self.orders:
                    self.stats["unknown_change"] += 1
                self._set_order(oid, side, pt, amount, touched)
                w.l3(m, 1 if ev == "order_created" else 2, side, oid, pt, amount)
            self._emit_levels(w, m, touched)
            w.bbo_if_changed(m, ts, rx, self.book, self.stats)
            self.stats["orders"] += 1
        elif ev == "trade":
            ts = int(d["microtimestamp"]) * 1000
            tid = int(d["id"])
            b, s = int(d["buy_order_id"]), int(d["sell_order_id"])
            agg = 1 if b > s else -1               # the later order is the taker
            if int(d.get("type", 0 if agg > 0 else 1)) != (0 if agg > 0 else 1):
                self.stats["type_disagree"] += 1
            maker = s if agg > 0 else b
            m = w.msg(ts, rx, tid, 1)
            w.trade(m, ts, rx, to_ticks(d["price_str"] if "price_str" in d else d["price"]),
                    float(d["amount_str"] if "amount_str" in d else d["amount"]), agg, tid, maker)
            self.stats["trades"] += 1

    def feed(self, rec: dict, w: HourWriter):
        kind = rec["kind"]
        rx = int(rec["rx"])
        msg = rec["msg"]
        if kind == "meta":
            if msg.get("event") == "connect" and self.synced:
                # the recorder reconnected: the stream has a hole, a new snapshot follows; stop applying until then
                self.synced = False
                self.buffer = []
                self.stats["reconnects"] += 1
            return
        if kind == "snapshot":
            self._load_snapshot(msg, w, rx)
            return
        if kind != "ws":
            return
        if not self.synced:
            self.buffer.append((rx, msg))
            if len(self.buffer) > 200000:
                self.buffer = self.buffer[-100000:]
            return
        self._apply_ws(msg, w, rx)

    def carry(self, w: HourWriter, ts: int, rx: int):
        if self.synced:
            m = w.msg(ts, rx, 0, 2)
            for s, sb in ((0, self.book.bids), (1, self.book.asks)):
                for p, q in sb.items():
                    w.l2(m, s, p, q)
            for oid, (s, pt, a) in self.orders.items():
                w.l3(m, 1, s, oid, pt, a)
            w.bbo_if_changed(m, ts, rx, self.book, self.stats)


# ----------------------------------------------------------------------------------------------
# Binance bookTicker (top of book only)
# ----------------------------------------------------------------------------------------------
class BinanceBboBuilder:
    venue = "binance_bbo"

    def __init__(self):
        self.stats = {"bbo": 0}
        self.synced = True

    def feed(self, rec: dict, w: HourWriter):
        if rec["kind"] != "ws":
            return
        d = rec["msg"].get("data", {})
        if "b" not in d:
            return
        rx = int(rec["rx"])
        m = w.msg(rx, rx, int(d["u"]), 0)
        w.bbo_raw(m, rx, rx, float(d["b"]), float(d["a"]), float(d["B"]), float(d["A"]))
        self.stats["bbo"] += 1

    def carry(self, w: HourWriter, ts: int, rx: int):
        pass


BUILDERS = {"binance": BinanceBuilder, "coinbase": CoinbaseBuilder, "bitstamp": BitstampBuilder, "binance_bbo": BinanceBboBuilder}


def build_venue(raw_root: str, out_dir: str, venue: str, files: list[str] | None = None, skip_done: bool = True,
                log=print) -> list[dict]:
    """Rebuild one venue hour by hour. Hours are processed in order and the book state carries across files; with
    skip_done, hours whose msgs parquet exists are skipped only when they are the leading ones (the state must be
    rebuilt from the first unprocessed hour's own reset)."""
    files = files if files is not None else raw.hour_files(raw_root, venue)
    builder = BUILDERS[venue]()
    reports = []
    for i, path in enumerate(files):
        hour = raw.hour_key(path)
        done = os.path.exists(os.path.join(out_dir, venue, f"{hour}_msgs.parquet"))
        if skip_done and done and not builder.synced is False and i == 0:
            # cannot skip: the state of the next hour depends on this one. Rebuild quickly instead.
            pass
        stats = raw.ReadStats()
        w = HourWriter(out_dir, venue, hour, with_l3=(venue == "bitstamp"))
        first = True
        for rec in raw.iter_lines(path, stats):
            if first:
                first = False
                builder.carry(w, int(rec["rx"]), int(rec["rx"]))
            builder.feed(rec, w)
        sizes = w.write()
        rep = {"venue": venue, "hour": hour, "file": os.path.relpath(path, raw_root).replace("\\", "/"),
               "raw_bytes": os.path.getsize(path), "lines": stats.lines, "bad_json": stats.bad_json,
               "truncated": stats.truncated, **{f"rows_{k}": v for k, v in sizes.items()}, **dict(builder.stats)}
        reports.append(rep)
        log(f"{venue} {hour}: {stats.lines} lines -> " + ", ".join(f"{k} {v}" for k, v in sizes.items()) +
            (" [truncated]" if stats.truncated else ""))
    return reports


# ----------------------------------------------------------------------------------------------
def hours(out_dir: str, venue: str) -> list[str]:
    d = os.path.join(out_dir, venue)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-len("_msgs.parquet")] for f in os.listdir(d) if f.endswith("_msgs.parquet"))


def load_hour(out_dir: str, venue: str, hour: str, tables=("msgs", "l2", "trades", "bbo")) -> dict:
    out = {}
    for t in tables:
        p = os.path.join(out_dir, venue, f"{hour}_{t}.parquet")
        if os.path.exists(p):
            out[t] = pq.read_table(p).to_pandas()
    return out


def load_concat(out_dir: str, venue: str, table: str, hours_: list[str] | None = None):
    import pandas as pd
    hs = hours_ if hours_ is not None else hours(out_dir, venue)
    parts = []
    for h in hs:
        p = os.path.join(out_dir, venue, f"{h}_{table}.parquet")
        if os.path.exists(p):
            parts.append(pq.read_table(p).to_pandas())
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
