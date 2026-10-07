"""Known-answer tests for the queue-position models (worked examples of the hftbacktest rules)."""
import math

from cvq.vendor.queue_model import QueueModel, QueuePos


def test_trade_consumes_the_front_and_fills_past_zero():
    qm = QueueModel("naive_fifo")
    q = qm.new_order(10.0)                 # 10 lots ahead of us
    qm.trade(q, 4.0)
    assert q.front == 6.0 and QueueModel.executable(q) == 0.0
    qm.trade(q, 8.0)                       # 2 lots more than the queue ahead: 2 lots of ours execute
    assert math.isclose(QueueModel.executable(q), 2.0)


def test_depth_increase_never_moves_us_forward():
    qm = QueueModel("naive_fifo")
    q = qm.new_order(10.0)
    qm.depth(q, 10.0, 15.0)                # arrivals join behind us
    assert q.front == 10.0


def test_naive_fifo_splits_a_cancel_by_queue_share():
    qm = QueueModel("naive_fifo")
    q = qm.new_order(10.0)
    # we are 10 ahead, 10 behind (level 20); a 4-lot cancel is behind us with probability 10/20
    qm.depth(q, 20.0, 16.0)
    assert math.isclose(q.front, 10.0 - 0.5 * 4.0)


def test_power_prob_puts_more_of_the_cancel_behind_us():
    naive = QueueModel("naive_fifo")
    power = QueueModel("power_prob", n=3.0)
    qn, qp = naive.new_order(5.0), power.new_order(5.0)
    naive.depth(qn, 20.0, 16.0)            # back = 15, front = 5
    power.depth(qp, 20.0, 16.0)
    # P(behind) naive = 15/20 = 0.75, power = 15^3/(15^3+5^3) = 0.964
    assert math.isclose(qn.front, 5.0 - 0.25 * 4.0)
    assert math.isclose(qp.front, 5.0 - (1 - 15**3 / (15**3 + 5**3)) * 4.0)
    assert qp.front > qn.front


def test_risk_averse_only_advances_on_trades():
    qm = QueueModel("risk_averse")
    q = qm.new_order(10.0)
    qm.depth(q, 20.0, 12.0)                # an 8-lot cancel: all assumed behind us
    assert q.front == 10.0
    qm.depth(q, 12.0, 6.0)                 # the level is now smaller than our estimate: capped
    assert q.front == 6.0
    qm.trade(q, 6.0)
    assert q.front == 0.0


def test_recorded_trades_are_not_double_counted_as_cancels():
    qm = QueueModel("naive_fifo")
    q = qm.new_order(10.0)
    qm.trade(q, 3.0)                       # front 7, cum_trade 3
    qm.depth(q, 20.0, 17.0)                # the depth update only reflects that trade: no cancel inferred
    assert math.isclose(q.front, 7.0)
    assert q.cum_trade == 0.0


def test_cancel_larger_than_the_back_eats_into_the_front():
    qm = QueueModel("risk_averse")
    q = qm.new_order(10.0)
    qm.depth(q, 10.0, 0.0)                 # the whole level vanished without trades: we are now alone at the front
    assert q.front == 0.0 and QueueModel.executable(q) == 0.0


def test_unknown_model_rejected():
    try:
        QueueModel("fifo_plus")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
