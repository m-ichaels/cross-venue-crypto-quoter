import numpy as np

from cvq.vendor import leadlag as LL


def test_hy_synchronous_equals_realised_covariance():
    rng = np.random.default_rng(0)
    t = np.arange(500, dtype=float)
    x = np.cumsum(rng.standard_normal(500))
    y = np.cumsum(rng.standard_normal(500))
    assert abs(LL.hy_cov(t, x, t, y, 0.0) - np.sum(np.diff(x) * np.diff(y))) < 1e-9
    assert abs(LL.hy_cov(t, x, t, y, 1.0) - np.sum(np.diff(x)[:-1] * np.diff(y)[1:])) < 1e-9


def test_hrv_recovers_known_lag_on_asynchronous_ticks_and_flips_with_order():
    tx, x, ty, y = LL.simulate_lagged(n=20000, lag=2.0, rho=0.8, seed=3)
    grid = np.arange(-6, 6.01, 0.25)
    s = LL.summarise(LL.contrast(tx, x, ty, y, grid))
    assert abs(s["theta_star"] - 2.0) <= 0.5
    assert s["llr"] > 2.0 and s["rho_star"] > 0.3
    s2 = LL.summarise(LL.contrast(ty, y, tx, x, grid))
    assert abs(s2["theta_star"] + 2.0) <= 0.5


def test_block_bootstrap_interval_contains_estimate():
    tx, x, ty, y = LL.simulate_lagged(n=12000, lag=1.5, rho=0.7, seed=4)
    grid = np.arange(-5, 5.01, 0.25)
    bx, by = (tx // 1000).astype(int), (ty // 1000).astype(int)
    covs, sxs, sys_, used = LL.per_block(tx, x, ty, y, bx, by, grid)
    out, pooled = LL.bootstrap(covs, sxs, sys_, grid, n_boot=100)
    assert out["n_blocks"] == len(used) >= 10
    assert out["theta_lo"] <= out["theta_star"] <= out["theta_hi"]
    assert out["p_x_leads"] > 0.9


def test_series_from_ticks_collapses_ties_and_unchanged_prices():
    t_ns = np.array([0, 0, 250_000_000, 1_000_000_000, 2_000_000_000], np.int64) + 10**18
    px = np.array([100.0, 100.5, 101.0, 101.0, 101.5])
    t, lx = LL.series_from_ticks(t_ns, px, 10**18)
    assert len(t) == 3                                  # tie collapsed, unchanged price dropped
    assert abs(lx[0] - np.log(100.5)) < 1e-12 and abs(t[1] - 0.25) < 1e-9
    c = LL.contrast(t, lx, t, lx, np.array([0.0]))
    assert abs(c.rho.iloc[0] - 1.0) < 1e-12
