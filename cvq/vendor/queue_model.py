"""Queue-position models for a passive order resting at a price level whose total size we see but whose order-by-order
composition we do not (L2 data). Queue position is therefore a *model*, not an observation, and the replay reports
every number under all three.

NOTICE: Python port of include/lobsim/queue_model.hpp from github.com/m-ichaels/lob-execution-sim (same owner), which
reproduces the update rules of hftbacktest (nkaz001/hftbacktest, src/backtest/models/queue.rs):

  trade(q)          front -= q                       a trade at our price consumes the queue ahead of us first
  depth(prev, now)  chg = prev - now - cum_trade_since_last_depth
      increase      front = min(front, now)          arrivals join behind us
      decrease      prob = P(the cancel was behind us) = f(back) / (f(back) + f(front))
                    front = min(front - (1 - prob) * chg + min(back - prob * chg, 0), now)
  fill              when front < 0, |front| lots of our order have executed (bounded by what is left of it)

  naive_fifo   f(x) = x       cancellations uniformly distributed along the queue
  power_prob   f(x) = x ** n  hftbacktest PowerProbQueueFunc, default n = 3 (cancels more likely at the back)
  risk_averse  front = min(front, now) on any depth change: every cancellation is assumed to be behind us,
               only trades advance us

Assumptions, stated: the queue is FIFO at one price; a trade reported at our price hits the queue ahead of us before
it can reach us; the model never sees hidden/iceberg liquidity; a decrease split between trades and cancels is
attributed with the recorded trades first (cum_trade) and the remainder treated as cancellations.

The L3 exact model (Bitstamp, order ids known) lives in cvq.replay, not here: it is an observation, not a model.
"""
from __future__ import annotations

from dataclasses import dataclass

MODELS = ("naive_fifo", "power_prob", "risk_averse")


@dataclass
class QueuePos:
    front: float = 0.0        # estimated size ahead of us
    cum_trade: float = 0.0    # trades applied since the last depth update at this level


class QueueModel:
    def __init__(self, kind: str = "naive_fifo", n: float = 3.0):
        if kind not in MODELS:
            raise ValueError(f"unknown queue model {kind!r}; one of {MODELS}")
        self.kind = kind
        self.n = n

    def new_order(self, level_qty: float) -> QueuePos:
        return QueuePos(front=float(level_qty), cum_trade=0.0)

    def trade(self, q: QueuePos, traded: float) -> None:
        q.front -= traded
        q.cum_trade += traded

    def probability(self, front: float, back: float) -> float:
        """P(a cancellation of one unit came from behind us)."""
        if self.kind == "naive_fifo":
            fb, ff = back, front
        else:
            fb, ff = back ** self.n, front ** self.n
        if fb + ff <= 0:
            return 1.0
        return fb / (fb + ff)

    def depth(self, q: QueuePos, prev_qty: float, new_qty: float) -> None:
        chg = prev_qty - new_qty - q.cum_trade
        q.cum_trade = 0.0
        if self.kind == "risk_averse" or chg <= 0:
            q.front = min(q.front, new_qty)
            return
        front = max(q.front, 0.0)
        back = max(prev_qty - front, 0.0)
        prob = self.probability(front, back)
        est = front - (1.0 - prob) * chg + min(back - prob * chg, 0.0)
        q.front = min(est, new_qty)

    @staticmethod
    def executable(q: QueuePos) -> float:
        """Size of our order that has executed once the estimated front is negative."""
        return -q.front if q.front < 0 else 0.0
