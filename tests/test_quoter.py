import math

from cvq.quoter import TICK, EwmaVol, QuoterParams, ceil_tick, floor_tick, target_quotes


def test_ticks():
    assert floor_tick(83000.019) == 83000.01
    assert ceil_tick(83000.011) == 83000.02
    assert floor_tick(83000.01) == 83000.01 and ceil_tick(83000.01) == 83000.01


def test_flat_inventory_quotes_are_symmetric_and_post_only():
    prm = QuoterParams(c_delta=0.5, T=16.0)                   # delta = 0.5 * sigma * 4 = 2 sigma
    m, bid, ask = 80000.0, 79999.99, 80000.01
    b, a, delta, kappa = target_quotes(m, 0, 1.0, bid, ask, prm)   # sigma 1 bp/sqrt(s) -> delta 2 bp = $16
    assert math.isclose(delta, 2.0)
    assert math.isclose(m - b, a - m, abs_tol=TICK + 1e-9)
    assert b < ask and a > bid                                # never crosses
    assert math.isclose(b, floor_tick(m * (1 - 2e-4)))


def test_long_inventory_skews_both_quotes_down():
    prm = QuoterParams(c_delta=0.5, c_q=0.25, T=16.0)
    m, bid, ask = 80000.0, 79999.99, 80000.01
    b0, a0, _, _ = target_quotes(m, 0, 1.0, bid, ask, prm)
    b2, a2, _, kappa = target_quotes(m, 2, 1.0, bid, ask, prm)   # long 2 lots
    assert math.isclose(kappa, 1.0)                           # 0.25 * 1 * 4 bp per lot
    assert b2 < b0 and a2 <= a0 or a2 == max(ceil_tick(m * (1 - 2e-4 + 2e-4)), bid + TICK)
    assert b0 - b2 >= 2 * kappa * 1e-4 * m * 0.9              # about 2 bp lower


def test_inventory_bound_removes_one_side():
    prm = QuoterParams(max_inventory=3)
    b, a, _, _ = target_quotes(80000.0, 3, 1.0, 79999.0, 80001.0, prm)
    assert b is None and a is not None
    b, a, _, _ = target_quotes(80000.0, -3, 1.0, 79999.0, 80001.0, prm)
    assert a is None and b is not None


def test_half_spread_never_tighter_than_the_venue_or_a_tick():
    prm = QuoterParams(c_delta=0.0)
    b, a, delta, _ = target_quotes(80000.0, 0, 1.0, 79990.0, 80010.0, prm)   # venue half spread 10 $ = 1.25 bp
    assert math.isclose(delta, 10.0 / 80000.0 * 1e4)
    assert b <= 79990.0 and a >= 80010.0
    b, a, delta, _ = target_quotes(80000.0, 0, 0.0, 79999.99, 80000.01, prm)
    assert delta >= TICK / 80000.0 * 1e4 - 1e-12


def test_ewma_vol_converges_to_the_generating_sigma():
    import numpy as np
    rng = np.random.default_rng(0)
    v = EwmaVol(halflife_s=60.0, sigma0_bp=5.0)
    m = 80000.0
    for i in range(20000):
        m *= math.exp(rng.standard_normal() * 1e-4)          # 1 bp per second
        v.update(float(i), m)
    assert 0.8 < v.sigma_bp < 1.25
