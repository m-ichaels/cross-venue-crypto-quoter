"""Book builders on hand-made raw messages: the normalised tables must be exactly what the messages imply."""
import gzip
import json
import os

import numpy as np

from cvq import books, raw


def _write_raw(tmp_path, venue, records):
    d = tmp_path / venue / "2026-10-07"
    d.mkdir(parents=True)
    p = d / "15.jsonl.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        for rx, kind, msg in records:
            f.write(json.dumps({"rx": rx, "venue": venue, "kind": kind, "msg": msg}) + "\n")
    return str(tmp_path)


def _depth(E, U, u, b=(), a=()):
    return {"stream": "btcusdt@depth@100ms", "data": {"e": "depthUpdate", "E": E, "s": "BTCUSDT", "U": U, "u": u,
                                                     "b": [[f"{p:.8f}", f"{q:.8f}"] for p, q in b],
                                                     "a": [[f"{p:.8f}", f"{q:.8f}"] for p, q in a]}}


def test_binance_sync_rule_and_tables(tmp_path):
    recs = [
        (1, "ws", _depth(1000, 1, 2, b=[(100.00, 1.0)])),                  # before the snapshot: u <= L, dropped
        (2, "ws", _depth(1100, 3, 5, b=[(100.01, 2.0)])),                  # U <= L+1 <= u: first applied event
        (3, "snapshot", {"lastUpdateId": 4, "bids": [["100.00", "1.0"], ["99.99", "3.0"]], "asks": [["100.02", "0.5"]]}),
        (4, "ws", _depth(1200, 6, 7, a=[(100.02, 0.0), (100.03, 0.7)])),   # best ask removed, new one
        (5, "ws", {"stream": "btcusdt@trade", "data": {"e": "trade", "E": 1250, "s": "BTCUSDT", "t": 77, "p": "100.01000000",
                                                       "q": "0.50000000", "T": 1249, "m": True, "M": True}}),
        (6, "ws", _depth(1300, 9, 9, b=[(100.01, 1.5)])),                  # gap (expected U = 8): book invalid
        (7, "ws", _depth(1400, 10, 10, b=[(100.01, 1.4)])),
    ]
    root = _write_raw(tmp_path, "binance", recs)
    out = str(tmp_path / "derived")
    rep = books.build_venue(root, out, "binance", log=lambda *a: None)[0]
    assert rep["gaps"] == 1 and rep["resyncs"] == 1
    t = books.load_hour(out, "binance", "2026-10-07T15")
    msgs, l2, tr, bbo = t["msgs"], t["l2"], t["trades"], t["bbo"]
    assert list(msgs.kind) == [2, 0, 0, 1]                      # reset, 2 depth updates, 1 trade; the post-gap ones dropped
    reset_rows = l2[l2.msg == 0]
    assert len(reset_rows) == 3 and set(np.round(reset_rows.price, 2)) == {100.00, 99.99, 100.02}
    first = l2[l2.msg == 1]
    assert len(first) == 1 and abs(first.price.iloc[0] - 100.01) < 1e-9 and first.qty.iloc[0] == 2.0
    assert len(bbo) == 3                                          # at the reset, after msg 1 (bid 100.01) and after msg 2 (ask 100.03)
    assert abs(bbo.bid.iloc[0] - 100.00) < 1e-9 and abs(bbo.ask.iloc[0] - 100.02) < 1e-9 and bbo.msg.iloc[0] == 0
    assert abs(bbo.bid.iloc[1] - 100.01) < 1e-9 and abs(bbo.ask.iloc[1] - 100.02) < 1e-9
    assert abs(bbo.ask.iloc[2] - 100.03) < 1e-9 and abs(bbo.ask_qty.iloc[2] - 0.7) < 1e-9
    assert msgs.ts.iloc[1] == 1100 * 1_000_000 and msgs.ts.iloc[3] == 1249 * 1_000_000
    assert len(tr) == 1 and tr.aggressor.iloc[0] == -1 and tr.trade_id.iloc[0] == 77 and abs(tr.qty.iloc[0] - 0.5) < 1e-12


def test_coinbase_snapshot_updates_and_maker_side(tmp_path):
    recs = [
        (1, "ws", {"type": "subscriptions"}),
        (2, "snapshot", {"type": "snapshot", "product_id": "BTC-USD", "bids": [["100.00", "1.0"]], "asks": [["100.05", "2.0"]],
                         "time": "2026-10-07T15:00:00.000000Z"}),
        (3, "ws", {"type": "l2update", "product_id": "BTC-USD", "changes": [["buy", "100.01", "0.30000000"], ["sell", "100.05", "0.00000000"],
                                                                           ["sell", "100.04", "1.00000000"]], "time": "2026-10-07T15:00:00.050000Z"}),
        (4, "ws", {"type": "match", "trade_id": 5, "side": "sell", "size": "0.1", "price": "100.04", "product_id": "BTC-USD",
                   "sequence": 9, "time": "2026-10-07T15:00:00.060000Z"}),
        (5, "ws", {"type": "match", "trade_id": 7, "side": "buy", "size": "0.2", "price": "100.01", "product_id": "BTC-USD",
                   "sequence": 11, "time": "2026-10-07T15:00:00.070000Z"}),
    ]
    root = _write_raw(tmp_path, "coinbase", recs)
    out = str(tmp_path / "derived")
    rep = books.build_venue(root, out, "coinbase", log=lambda *a: None)[0]
    assert rep["gaps"] == 1                                       # trade_id 5 -> 7
    t = books.load_hour(out, "coinbase", "2026-10-07T15")
    bbo, tr, l2 = t["bbo"], t["trades"], t["l2"]
    assert len(bbo) == 2
    assert abs(bbo.bid.iloc[1] - 100.01) < 1e-9 and abs(bbo.ask.iloc[1] - 100.04) < 1e-9
    assert list(tr.aggressor) == [1, -1]                          # maker sold -> buyer-initiated; maker bought -> seller-initiated
    assert t["msgs"].ts.iloc[1] == books.iso_ns("2026-10-07T15:00:00.050000Z")
    assert (l2[l2.msg == 1].qty == 0).sum() == 1                  # the removed ask level is written with qty 0


def _bs(ev, oid, order_type, price, amount, mt, traded="0"):
    return {"event": ev, "channel": "live_orders_btcusd",
            "data": {"id": oid, "id_str": str(oid), "order_type": order_type, "price": price, "price_str": f"{price:.2f}",
                     "amount": amount, "amount_str": f"{amount:.8f}", "amount_traded": traded, "microtimestamp": str(mt), "datetime": str(mt // 10**6)}}


def test_bitstamp_l3_aggregation_snapshot_replay_and_aggressor(tmp_path):
    recs = [
        (1, "meta", {"event": "connect"}),
        (2, "ws", _bs("order_created", 11, 0, 100.00, 1.0, 1_000_000)),          # before the snapshot and older than it: in the snapshot already
        (3, "ws", _bs("order_created", 12, 1, 100.03, 2.0, 1_000_000)),
        (4, "ws", _bs("order_created", 13, 0, 100.01, 0.5, 3_000_000)),          # newer than the snapshot: replayed onto it
        (5, "snapshot", {"timestamp": "2", "microtimestamp": "2000000",
                         "bids": [["100.00", "1.00000000", "11"], ["100.00", "4.00000000", "10"]], "asks": [["100.03", "2.00000000", "12"]]}),
        (6, "ws", _bs("order_changed", 10, 0, 100.00, 3.0, 4_000_000, traded="1.00000000")),   # partial fill of order 10
        (7, "ws", {"event": "trade", "channel": "live_trades_btcusd", "data": {"id": 900, "amount": 1.0, "amount_str": "1.00000000",
                   "price": 100.00, "price_str": "100.00", "type": 1, "microtimestamp": "4000000", "buy_order_id": 10, "sell_order_id": 99}}),
        (8, "ws", _bs("order_deleted", 11, 0, 100.00, 1.0, 5_000_000)),
        (9, "ws", _bs("order_deleted", 10, 0, 100.00, 3.0, 6_000_000)),         # level 100.00 now empty: no residue level
    ]
    root = _write_raw(tmp_path, "bitstamp", recs)
    out = str(tmp_path / "derived")
    rep = books.build_venue(root, out, "bitstamp", log=lambda *a: None)[0]
    assert rep["snapshot_orders"] == 3 and rep["type_disagree"] == 0
    t = books.load_hour(out, "bitstamp", "2026-10-07T15", ("msgs", "l2", "trades", "bbo", "l3"))
    msgs, l2, tr, bbo, l3 = t["msgs"], t["l2"], t["trades"], t["bbo"], t["l3"]
    assert msgs.kind.iloc[0] == 2 and len(l3[l3.msg == 0]) == 3   # the reset carries the three snapshot orders
    # after the replayed order 13 the best bid is 100.01 x 0.5; the aggregate at 100.00 is 5.0
    r1 = l2[l2.msg == 1]
    assert abs(r1.price.iloc[0] - 100.01) < 1e-9 and abs(r1.qty.iloc[0] - 0.5) < 1e-9
    assert abs(bbo.bid.iloc[-1] - 100.01) < 1e-9
    # order 10 changed 4.0 -> 3.0: level 100.00 = 1.0 + 3.0
    r2 = l2[l2.msg == 2]
    assert abs(r2.qty.iloc[0] - 4.0) < 1e-9
    # the trade: sell_order_id 99 > buy_order_id 10 -> seller-initiated, maker = 10
    assert tr.aggressor.iloc[0] == -1 and tr.maker_order_id.iloc[0] == 10
    # after both deletions the 100.00 level is exactly zero (no float residue) and the final bbo bid is 100.01
    last_level = l2[(np.round(l2.price, 2) == 100.00)].qty.iloc[-1]
    assert last_level == 0.0
    assert set(l3.action) == {1, 2, 3}


def test_raw_reader_tolerates_a_torn_tail(tmp_path):
    d = tmp_path / "x" / "2026-10-07"
    d.mkdir(parents=True)
    p = d / "15.jsonl.gz"
    with gzip.open(p, "wb") as f:
        f.write(b'{"rx":1,"venue":"x","kind":"meta","msg":{}}\n{"rx":2,"venue":"x","kind":"ws","msg":{"a":1}}\n{"rx":3,"ven')
    st = raw.ReadStats()
    recs = list(raw.iter_lines(str(p), st))
    assert len(recs) == 2 and st.bad_json == 1 and st.truncated
    assert raw.hour_key(str(p)) == "2026-10-07T15"
