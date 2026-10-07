"""The replay on a hand-made tape and the P&L identity."""
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from cvq import books, pnl, replay
from cvq.quoter import QuoterParams

NS = 1_000_000_000


def _write_hour(derived, venue, hour, msgs, l2, trades, bbo, l3=None):
    d = derived / venue
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(msgs), str(d / f"{hour}_msgs.parquet"))
    pq.write_table(pa.table(l2), str(d / f"{hour}_l2.parquet"))
    pq.write_table(pa.table(trades), str(d / f"{hour}_trades.parquet"))
    pq.write_table(pa.table(bbo), str(d / f"{hour}_bbo.parquet"))
    if l3 is not None:
        pq.write_table(pa.table(l3), str(d / f"{hour}_l3.parquet"))


def _tape(tmp_path):
    """A flat book 100.00 / 100.02 for 30 s, then a seller sweeps the bid side down to 99.90 at t = 30 s, then quiet.

    One depth message per second keeps the top of book constant (so the quoter joins the bid at 100.00 and the ask at
    100.02 with the venue's half spread); the sweep is a trade at 99.95 (through our 100.00 bid) followed by a depth
    update moving the best bid to 99.90 and the ask to 99.92."""
    t0 = 1_700_000_000 * NS
    ts, kind, l2_msg, l2_side, l2_px, l2_qty = [], [], [], [], [], []
    bbo_ts, bbo_bid, bbo_ask, bbo_msg = [], [], [], []
    # reset with the full book
    ts.append(t0); kind.append(2)
    for side, px, q in ((0, 100.00, 5.0), (0, 99.99, 5.0), (0, 99.90, 5.0), (1, 100.02, 5.0), (1, 100.03, 5.0)):
        l2_msg.append(0); l2_side.append(side); l2_px.append(px); l2_qty.append(q)
    bbo_ts.append(t0); bbo_bid.append(100.00); bbo_ask.append(100.02); bbo_msg.append(0)
    tr_ts, tr_px, tr_qty, tr_agg, tr_msg = [], [], [], [], []
    i = 1
    for s in range(1, 90):
        t = t0 + s * NS
        if s == 30:
            # the sweep: a sell trade prints at 99.95 (through 100.00), then the book shows the new top
            ts.append(t); kind.append(1); tr_ts.append(t); tr_px.append(99.95); tr_qty.append(3.0); tr_agg.append(-1); tr_msg.append(i); i += 1
            ts.append(t + 1_000_000); kind.append(0)
            for side, px, q in ((0, 100.00, 0.0), (0, 99.99, 0.0), (1, 99.92, 4.0), (1, 100.02, 0.0), (1, 100.03, 0.0)):
                l2_msg.append(i); l2_side.append(side); l2_px.append(px); l2_qty.append(q)
            bbo_ts.append(t + 1_000_000); bbo_bid.append(99.90); bbo_ask.append(99.92); bbo_msg.append(i); i += 1
            continue
        ts.append(t); kind.append(0)
        bid_px = 100.00 if s < 30 else 99.90
        l2_msg.append(i); l2_side.append(0); l2_px.append(bid_px); l2_qty.append(5.0 + 0.1 * (s % 3))
        i += 1
    msgs = {"ts": np.array(ts, np.int64), "rx": np.array(ts, np.int64), "seq": np.arange(len(ts), dtype=np.int64), "kind": np.array(kind, np.int8)}
    l2 = {"msg": np.array(l2_msg, np.int32), "side": np.array(l2_side, np.int8), "price": np.array(l2_px), "qty": np.array(l2_qty)}
    trades = {"ts": np.array(tr_ts, np.int64), "rx": np.array(tr_ts, np.int64), "price": np.array(tr_px), "qty": np.array(tr_qty),
              "aggressor": np.array(tr_agg, np.int8), "trade_id": np.arange(len(tr_ts), dtype=np.int64),
              "maker_order_id": -np.ones(len(tr_ts), np.int64), "msg": np.array(tr_msg, np.int32)}
    bbo = {"ts": np.array(bbo_ts, np.int64), "rx": np.array(bbo_ts, np.int64), "bid": np.array(bbo_bid), "ask": np.array(bbo_ask),
           "bid_qty": np.full(len(bbo_ts), 5.0), "ask_qty": np.full(len(bbo_ts), 5.0), "msg": np.array(bbo_msg, np.int32)}
    derived = tmp_path / "derived"
    _write_hour(derived, "toy", "2026-10-07T15", msgs, l2, trades, bbo)
    return str(derived), t0


def test_replay_fills_through_the_sweep_and_the_pnl_identity_holds(tmp_path):
    derived, t0 = _tape(tmp_path)
    prm = QuoterParams(latency_ms=0, signal=0, c_delta=0.0, T=1000.0, requote_tol_bp=50.0, episode_s=60.0)
    out = replay.run(derived, "toy", prm, queue_model="naive_fifo")
    fills, eps = out["fills"], out["episodes"]
    # the quoter joined the bid at 100.00 (venue half spread) and the sweep at t = 30 s filled it in full
    assert len(fills) == 1
    f = fills.iloc[0]
    assert f.side == 1 and abs(f.price - 100.00) < 1e-9 and abs(f.qty - prm.lot) < 1e-12 and f.reason == "through"
    assert abs(f.t - (t0 + 30 * NS)) <= 1_000_000
    # the episode (60 s) ended long 1 lot, flattened at the bid 99.90
    e = eps.iloc[0]
    assert abs(e.inv_end_lots - 1.0) < 1e-9 and abs(e.liq_px - 99.90) < 1e-9
    own = books.load_concat(derived, "toy", "bbo")
    own_ts, own_mid = own.ts.to_numpy(np.int64), (0.5 * (own.bid + own.ask)).to_numpy()
    fm = pnl.add_markouts(fills, eps, own_ts, own_mid)
    # mid at the fill is still the pre-sweep 100.01 (the depth update comes 1 ms later); 1 s later it is 99.91
    assert abs(fm.mid.iloc[0] - 100.01) < 1e-9 and abs(fm["mid_1s"].iloc[0] - 99.91) < 1e-9
    assert abs(fm["markout_1s_bp"].iloc[0] - (99.91 - 100.00) / 100.00 * 1e4) < 1e-9
    att = pnl.attribute(fm, eps, maker_bp=2.0, taker_bp=5.0, lot=prm.lot)
    a = att.iloc[0]
    assert abs(a.spread_bp - 1.0) < 1e-9                               # (100.01 - 100.00) / 100 * 1e4
    assert abs(a.adverse_bp - (100.01 - 99.91) / 100.0 * 1e4) < 1e-9   # 60 s mark-out capped at the episode end
    assert abs(a.fee_bp - 2.0) < 1e-12
    # identity: attributed P&L equals the realised episode P&L (marked at the end mid, flattened at the touch, fees paid)
    assert pnl.episode_pnl_check(att, eps, prm.lot, taker_bp=5.0) < 1e-9
    realised = prm.lot * (99.91 - 100.00) - prm.lot * (99.91 - 99.90) - 5.0e-4 * prm.lot * 99.91 - 2.0e-4 * prm.lot * 100.0
    assert abs(a.pnl_bp * a.notional / 1e4 - realised) < 1e-9


def test_latency_delays_the_placement_and_fills_still_count(tmp_path):
    derived, t0 = _tape(tmp_path)
    prm = QuoterParams(latency_ms=200, signal=0, c_delta=0.0, T=1000.0, requote_tol_bp=50.0, episode_s=60.0)
    out = replay.run(derived, "toy", prm, queue_model="risk_averse")
    assert len(out["fills"]) == 1 and out["stats"]["placed"] >= 2
    # the first order could only rest from decision + latency onwards
    assert out["fills"].iloc[0].t >= t0 + 200_000_000


def test_bootstrap_weighted_and_difference():
    f = pd.DataFrame({"episode": [0, 0, 1, 1, 2, 2], "notional": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0], "pnl_bp": [1.0, 3.0, 2.0, 2.0, 1.0, 3.0]})
    b = pnl.bootstrap_weighted(f, "pnl_bp", n_boot=200, seed=0)
    assert abs(b["mean"] - 2.0) < 1e-12 and b["lo"] <= 2.0 <= b["hi"] and b["n_episodes"] == 3
    g = f.assign(pnl_bp=f.pnl_bp + 1.0)
    d = pnl.bootstrap_difference(g, f, "pnl_bp", n_boot=200, seed=0)
    assert abs(d["diff"] - 1.0) < 1e-12 and abs(d["lo"] - 1.0) < 1e-9 and abs(d["hi"] - 1.0) < 1e-9
