#!/usr/bin/env python3
"""
Live public-websocket recorder for three BTC spot books.

  Binance spot      BTCUSDT  depth@100ms diff stream + trade stream, synchronised to a REST depth
                    snapshot (limit 5000) with the documented U/u rule (L2); optionally the real-time
                    bookTicker stream (best bid/ask on every change) as venue "binance_bbo".
  Coinbase Exchange BTC-USD  level2_batch (snapshot + 50 ms batched absolute-size updates) + matches
                    (L2, public; the unbatched `level2` and `full` channels need an API key since 2023).
  Bitstamp          btcusd   live_orders (order_created / order_changed / order_deleted with order ids
                    and microsecond timestamps) + live_trades (with buy/sell order ids): public L3.
                    A REST order_book?group=2 snapshot (rows carry order ids) seeds the L3 book.

Design rules:
  * every message is written to disk *raw*, before it is parsed, in the order received;
  * files are append-only gzip NDJSON rotated hourly:
        <out>/<venue>/<YYYY-MM-DD>/<HH>.jsonl.gz
    one JSON object per line:
        {"rx":<local receive time, ns since epoch>,"venue":"binance"|"coinbase"|"bitstamp",
         "kind":"ws"|"snapshot"|"meta","msg":<raw payload verbatim>}
  * the recorder keeps a Binance book only to detect sequence gaps and trigger a resync; the exact
    book is rebuilt offline by cvq.books from the raw files.
  * stops after --minutes, on SIGINT, or when the file <out>/STOP exists (checked every few seconds),
    closing every gzip member cleanly.

NOTICE: adapted from tools/recorder/recorder.py in github.com/m-ichaels/lob-execution-sim (same owner),
rewritten to gzip output, to use `requests` for REST (no aiohttp dependency) and to add the stop file.
"""
import argparse
import asyncio
import gzip
import json
import os
import signal
import time
from collections import deque
from datetime import datetime, timezone

import requests
import websockets

BINANCE_WS = "wss://stream.binance.com:9443/stream?streams="
BINANCE_REST = "https://api.binance.com/api/v3/depth"
COINBASE_WS = "wss://ws-feed.exchange.coinbase.com"
BITSTAMP_WS = "wss://ws.bitstamp.net"
BITSTAMP_REST = "https://www.bitstamp.net/api/v2/order_book/%s/"


def now_ns() -> int:
    return time.time_ns()


class RawLogger:
    """Append-only hourly gzip NDJSON writer. One instance per venue."""

    def __init__(self, root: str, venue: str, flush_every: float = 2.0, level: int = 6):
        self.root, self.venue = root, venue
        self.fh = None
        self.cur_hour = None
        self.n_lines = 0
        self.n_bytes = 0          # uncompressed bytes written
        self.last_flush = time.monotonic()
        self.flush_every = flush_every
        self.level = level
        self.paths = []

    def _path_for(self, rx_ns: int) -> str:
        dt = datetime.fromtimestamp(rx_ns / 1e9, tz=timezone.utc)
        d = os.path.join(self.root, self.venue, dt.strftime("%Y-%m-%d"))
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, dt.strftime("%H") + ".jsonl.gz")

    def write(self, kind: str, raw: str, rx_ns=None):
        rx_ns = rx_ns if rx_ns is not None else now_ns()
        hour = rx_ns // (3600 * 10**9)
        if hour != self.cur_hour:
            if self.fh:
                self.fh.close()
            p = self._path_for(rx_ns)
            # append mode: a restart within the same hour adds a new gzip member, which gzip.open reads through
            self.fh = gzip.open(p, "ab", compresslevel=self.level)
            self.paths.append(p)
            self.cur_hour = hour
        line = '{"rx":%d,"venue":"%s","kind":"%s","msg":%s}\n' % (rx_ns, self.venue, kind, raw.strip())
        b = line.encode("utf-8")
        self.fh.write(b)
        self.n_lines += 1
        self.n_bytes += len(b)
        t = time.monotonic()
        if t - self.last_flush > self.flush_every:
            self.fh.flush()
            self.last_flush = t

    def meta(self, event: str, **kw):
        kw["event"] = event
        self.write("meta", json.dumps(kw, separators=(",", ":"), default=str))

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh = None


def _rest_get(url, params=None, timeout=20):
    r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": "cvq-recorder/0.1"})
    r.raise_for_status()
    return r.text


async def rest_get(url, params=None):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _rest_get(url, params))


# ----------------------------------------------------------------------------------------------
# Binance
# ----------------------------------------------------------------------------------------------
class BinanceBook:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.last_u = None

    def load_snapshot(self, snap):
        self.bids = {p: q for p, q in snap["bids"] if float(q) > 0}
        self.asks = {p: q for p, q in snap["asks"] if float(q) > 0}
        self.last_u = snap["lastUpdateId"]

    def apply(self, ev):
        for side, book in (("b", self.bids), ("a", self.asks)):
            for p, q in ev[side]:
                if float(q) == 0.0:
                    book.pop(p, None)
                else:
                    book[p] = q
        self.last_u = ev["u"]


async def record_binance(symbol: str, log: RawLogger, stop: asyncio.Event, stats: dict):
    """
    Synchronisation (Binance spot docs, "How to manage a local order book correctly"):
      1. open the diff stream and buffer events; 2. GET depth?limit=5000 -> lastUpdateId = L;
      3. drop buffered events with u <= L; 4. the first processed event must satisfy U <= L+1 <= u;
      5. thereafter every event must have U == previous u + 1, otherwise resync from step 2.
    """
    sym_l = symbol.lower()
    url = BINANCE_WS + "%s@depth@100ms/%s@trade" % (sym_l, sym_l)
    backoff = 1.0
    st = stats.setdefault("binance", {"ws": 0, "gaps": 0, "resyncs": 0, "drift_ms": deque(maxlen=2000)})
    while not stop.is_set():
        book = BinanceBook()
        buffer = deque()
        synced = False
        snap = None
        L = None
        try:
            log.meta("connect", url=url)
            async with websockets.connect(url, max_size=2**24, ping_interval=20, ping_timeout=20) as ws:
                backoff = 1.0
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        log.meta("recv_timeout")
                        break
                    rx = now_ns()
                    log.write("ws", raw, rx)  # raw first, always
                    st["ws"] += 1
                    msg = json.loads(raw)
                    stream = msg.get("stream", "")
                    data = msg.get("data", {})
                    if "E" in data:
                        st["drift_ms"].append(rx / 1e6 - data["E"])
                    if not stream.endswith("@depth@100ms"):
                        continue
                    if synced:
                        if data["U"] != book.last_u + 1:
                            log.meta("gap", expected=book.last_u + 1, got=data["U"], u=data["u"])
                            st["gaps"] += 1
                            st["resyncs"] += 1
                            synced = False
                            buffer.clear()
                            buffer.append(data)
                            continue
                        book.apply(data)
                    else:
                        buffer.append(data)
                        if snap is None:
                            if len(buffer) < 3:
                                continue
                            snap_raw = await rest_get(BINANCE_REST, {"symbol": symbol, "limit": 5000})
                            snap = json.loads(snap_raw)
                            log.write("snapshot", snap_raw)
                            L = snap["lastUpdateId"]
                            book.load_snapshot(snap)
                        while buffer and buffer[0]["u"] <= L:
                            buffer.popleft()
                        if not buffer:
                            continue
                        first = buffer[0]
                        if not (first["U"] <= L + 1 <= first["u"]):
                            log.meta("resync_snapshot_too_old", L=L, U=first["U"], u=first["u"])
                            st["resyncs"] += 1
                            buffer.clear()
                            snap = None
                            await asyncio.sleep(1.0)  # depth?limit=5000 is weight 250: never hammer it
                            continue
                        ok = True
                        prev_u = None
                        for ev in buffer:
                            if prev_u is not None and ev["U"] != prev_u + 1:
                                ok = False
                                break
                            book.apply(ev)
                            prev_u = ev["u"]
                        buffer.clear()
                        snap = None
                        if not ok:
                            log.meta("gap_in_buffer")
                            st["gaps"] += 1
                            continue
                        synced = True
                        log.meta("synced", lastUpdateId=L, last_u=book.last_u)
        except (websockets.ConnectionClosed, requests.RequestException, OSError, asyncio.TimeoutError) as e:
            log.meta("disconnect", error=repr(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - keep recording no matter what
            log.meta("error", error=repr(e))
        if stop.is_set():
            break
        log.meta("reconnect_wait", seconds=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


async def record_binance_bbo(symbol: str, log: RawLogger, stop: asyncio.Event, stats: dict):
    """<symbol>@bookTicker: the best bid/ask (price, qty) pushed in real time on every change, with no event
    time; it is the sub-100 ms view of the Binance top of book that depth@100ms cannot give (lead-lag use)."""
    sym_l = symbol.lower()
    url = BINANCE_WS + "%s@bookTicker" % sym_l
    backoff = 1.0
    st = stats.setdefault("binance_bbo", {"ws": 0, "gaps": 0, "resyncs": 0, "drift_ms": deque(maxlen=2000)})
    while not stop.is_set():
        try:
            log.meta("connect", url=url)
            async with websockets.connect(url, max_size=2**24, ping_interval=20, ping_timeout=20) as ws:
                backoff = 1.0
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        log.meta("recv_timeout")
                        break
                    log.write("ws", raw, now_ns())
                    st["ws"] += 1
        except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            log.meta("disconnect", error=repr(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.meta("error", error=repr(e))
        if stop.is_set():
            break
        st["resyncs"] += 1
        log.meta("reconnect_wait", seconds=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


# ----------------------------------------------------------------------------------------------
# Coinbase Exchange
# ----------------------------------------------------------------------------------------------
async def record_coinbase(product: str, log: RawLogger, stop: asyncio.Event, stats: dict):
    """level2_batch: an initial `snapshot` then absolute price-level `l2update`s batched every 50 ms;
    matches: every trade with trade_id (consecutive per product) and the side of the maker; heartbeat."""
    st = stats.setdefault("coinbase", {"ws": 0, "gaps": 0, "resyncs": 0, "drift_ms": deque(maxlen=2000)})
    sub = json.dumps({"type": "subscribe", "product_ids": [product],
                      "channels": ["level2_batch", "matches", "heartbeat"]})
    backoff = 1.0
    while not stop.is_set():
        last_tid = None
        try:
            log.meta("connect", url=COINBASE_WS)
            async with websockets.connect(COINBASE_WS, max_size=2**24, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(sub)
                backoff = 1.0
                while not stop.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        log.meta("recv_timeout")
                        break
                    rx = now_ns()
                    msg = json.loads(raw)
                    t = msg.get("type")
                    log.write("snapshot" if t == "snapshot" else "ws", raw, rx)
                    st["ws"] += 1
                    if t == "error":
                        log.meta("error", error=msg)
                    tm = msg.get("time")
                    if tm:
                        try:
                            ev_ms = datetime.fromisoformat(tm.replace("Z", "+00:00")).timestamp() * 1e3
                            st["drift_ms"].append(rx / 1e6 - ev_ms)
                        except ValueError:
                            pass
                    tid = msg.get("trade_id")
                    if t == "match" and tid is not None:
                        if last_tid is not None and tid > last_tid + 1:
                            log.meta("gap", expected=last_tid + 1, got=tid)
                            st["gaps"] += 1
                        last_tid = tid
        except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            log.meta("disconnect", error=repr(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.meta("error", error=repr(e))
        if stop.is_set():
            break
        st["resyncs"] += 1
        log.meta("reconnect_wait", seconds=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


# ----------------------------------------------------------------------------------------------
# Bitstamp (order-by-order, public)
# ----------------------------------------------------------------------------------------------
async def record_bitstamp(pair: str, log: RawLogger, stop: asyncio.Event, stats: dict):
    """live_orders_<pair>: every order creation / change / deletion with order id, price, amount and
    microtimestamp; live_trades_<pair>: trades with buy_order_id / sell_order_id. After the stream is
    demonstrably live (>= 20 order events) a REST order_book?group=2 snapshot (rows [price, amount, order_id])
    is logged to seed the L3 book: it is newer than the first streamed event, so no deletion can fall
    into a hole before the subscription."""
    st = stats.setdefault("bitstamp", {"ws": 0, "gaps": 0, "resyncs": 0, "drift_ms": deque(maxlen=2000)})
    chans = ["live_orders_%s" % pair, "live_trades_%s" % pair]
    backoff = 1.0
    while not stop.is_set():
        try:
            log.meta("connect", url=BITSTAMP_WS)
            async with websockets.connect(BITSTAMP_WS, max_size=2**24, ping_interval=20, ping_timeout=20) as ws:
                for ch in chans:
                    await ws.send(json.dumps({"event": "bts:subscribe", "data": {"channel": ch}}))
                backoff = 1.0
                st["resyncs"] += 1
                need_snapshot = True
                n_order_events = 0
                while not stop.is_set():
                    if need_snapshot and n_order_events >= 20:
                        snap_raw = await rest_get(BITSTAMP_REST % pair, {"group": 2})
                        log.write("snapshot", snap_raw)
                        need_snapshot = False
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        log.meta("recv_timeout")
                        break
                    rx = now_ns()
                    log.write("ws", raw, rx)
                    st["ws"] += 1
                    msg = json.loads(raw)
                    ev = msg.get("event")
                    if ev == "bts:request_reconnect":
                        log.meta("request_reconnect")
                        break
                    d = msg.get("data") or {}
                    mt = d.get("microtimestamp")
                    if mt:
                        st["drift_ms"].append(rx / 1e6 - int(mt) / 1e3)
                    if ev in ("order_created", "order_deleted", "order_changed"):
                        n_order_events += 1
        except (websockets.ConnectionClosed, requests.RequestException, OSError, asyncio.TimeoutError) as e:
            log.meta("disconnect", error=repr(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.meta("error", error=repr(e))
        if stop.is_set():
            break
        log.meta("reconnect_wait", seconds=backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


# ----------------------------------------------------------------------------------------------
async def status_printer(stats: dict, logs, stop: asyncio.Event, every: float = 60.0):
    t0 = time.monotonic()
    last = {}
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=every)
        except asyncio.TimeoutError:
            pass
        el = time.monotonic() - t0
        parts = []
        for k, s in stats.items():
            rate = (s["ws"] - last.get(k, 0)) / every
            last[k] = s["ws"]
            d = sorted(s["drift_ms"])
            med = d[len(d) // 2] if d else float("nan")
            parts.append("%s: %d msgs (%.0f/s) gaps=%d resyncs=%d drift_med=%.0fms"
                         % (k, s["ws"], rate, s["gaps"], s["resyncs"], med))
        mb_raw = sum(l.n_bytes for l in logs) / 1e6
        mb_disk = 0.0
        for l in logs:
            for p in l.paths:
                try:
                    mb_disk += os.path.getsize(p) / 1e6
                except OSError:
                    pass
        print("[%6.1f min] raw %8.1f MB gz %7.1f MB | " % (el / 60, mb_raw, mb_disk) + " | ".join(parts), flush=True)


async def stop_file_watcher(path: str, stop: asyncio.Event):
    while not stop.is_set():
        if os.path.exists(path):
            print("stop file found: %s" % path, flush=True)
            stop.set()
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass


async def main_async(args):
    stop = asyncio.Event()
    stats = {}
    logs = []
    tasks = []
    if args.binance:
        lg = RawLogger(args.out, "binance")
        logs.append(lg)
        tasks.append(asyncio.create_task(record_binance(args.binance, lg, stop, stats)))
    if args.binance_bbo:
        lg = RawLogger(args.out, "binance_bbo")
        logs.append(lg)
        tasks.append(asyncio.create_task(record_binance_bbo(args.binance_bbo, lg, stop, stats)))
    if args.coinbase:
        lg = RawLogger(args.out, "coinbase")
        logs.append(lg)
        tasks.append(asyncio.create_task(record_coinbase(args.coinbase, lg, stop, stats)))
    if args.bitstamp:
        lg = RawLogger(args.out, "bitstamp")
        logs.append(lg)
        tasks.append(asyncio.create_task(record_bitstamp(args.bitstamp, lg, stop, stats)))
    tasks.append(asyncio.create_task(status_printer(stats, logs, stop)))
    tasks.append(asyncio.create_task(stop_file_watcher(os.path.join(args.out, "STOP"), stop)))

    def _stop(*_):
        stop.set()

    try:
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass
    if args.minutes > 0:
        async def timer():
            await asyncio.sleep(args.minutes * 60)
            print("duration reached", flush=True)
            stop.set()
        tasks.append(asyncio.create_task(timer()))
    print("recording to %s (binance=%s binance_bbo=%s coinbase=%s bitstamp=%s, %.0f min)" %
          (args.out, args.binance, args.binance_bbo, args.coinbase, args.bitstamp, args.minutes), flush=True)
    await stop.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for lg in logs:
        lg.meta("shutdown")
        lg.close()
    print("recorder stopped", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/raw", help="root directory for raw gzip NDJSON files")
    ap.add_argument("--binance", default="BTCUSDT", help="Binance spot symbol ('' to disable)")
    ap.add_argument("--binance-bbo", default="", help="Binance spot symbol for the real-time bookTicker stream ('' to disable)")
    ap.add_argument("--coinbase", default="BTC-USD", help="Coinbase Exchange product ('' to disable)")
    ap.add_argument("--bitstamp", default="btcusd", help="Bitstamp pair ('' to disable)")
    ap.add_argument("--minutes", type=float, default=0, help="stop after N minutes (0 = run until Ctrl-C / STOP file)")
    args = ap.parse_args(argv)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
