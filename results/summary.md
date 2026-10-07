# cross-venue-crypto-quoter — run summary (built 2026-10-07T15:41:27Z)

## Recording

| venue | hour files | raw lines | raw MB (gzip) | depth msgs | trades | gaps | resyncs | notes |
|---|---|---|---|---|---|---|---|---|
| binance | 1 (2026-10-07T15 .. 2026-10-07T15) | 66,501 | 2.6 | 8,950 | 57,537 | 0 | 1 | last file truncated |
| coinbase | 1 (2026-10-07T15 .. 2026-10-07T15) | 21,140 | 2.8 | 14,263 | 6,001 | 0 | 1 | last file truncated |
| bitstamp | 1 (2026-10-07T15 .. 2026-10-07T15) | 221,412 | 7.0 | 220,595 | 793 | 0 | 1 | L3 orders; unknown deletes 27; crossed-book messages skipped 219259; last file truncated |
| binance_bbo | 1 (2026-10-07T15 .. 2026-10-07T15) | 116,873 | 1.2 | 116,872 | 0 | 0 | 0 | last file truncated |

## P&L per fill (bp of notional; base: latency 50 ms, queue model naive_fifo, c_delta 0.5; 95 % intervals from resampling 15-minute episodes)

| venue | signal | fills | fills / h | entry tier | P&L entry | top tier | P&L top | mark-out 60 s | median age (s) |
|---|---|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | own mid | 179 | 401 | Regular user / VIP 0 (10.0 bp) | -11.87 [-11.98, -11.80] | VIP 9 (1.1 bp) | -2.81 [-2.88, -2.77] | -1.78 [-1.87, -1.65] | 1.6 |
| Binance BTCUSDT | re-marked off coinbase | 107 | 240 | Regular user / VIP 0 (10.0 bp) | -12.85 [-12.90, -12.77] | VIP 9 (1.1 bp) | -3.23 [-3.80, -2.96] | -1.96 [-2.17, -1.86] | 1.5 |
| Coinbase BTC-USD | own mid | 211 | 481 | $0K-$10K (40.0 bp) | -40.88 [-41.77, -40.46] | $400M+ (0.0 bp) | -0.60 [-0.88, -0.46] | -0.72 [-0.98, -0.61] | 0.9 |
| Coinbase BTC-USD | re-marked off binance | 240 | 547 | $0K-$10K (40.0 bp) | -41.44 [-42.75, -40.76] | $400M+ (0.0 bp) | -0.47 [-0.62, -0.40] | -0.49 [-0.51, -0.44] | 1.0 |
| Bitstamp BTC/USD | own mid | 138 | 237 | < $10K (30.0 bp) | -32.65 [-33.95, -32.10] | $1B+ (0.0 bp) | -1.17 [-1.48, -1.04] | -1.18 [-1.41, -0.74] | 2.4 |
| Bitstamp BTC/USD | re-marked off coinbase | 46 | 79 | < $10K (30.0 bp) | -37.19 [-38.40, -32.48] | $1B+ (0.0 bp) | -2.44 [-2.48, -2.43] | -1.97 [-10.37, -0.78] | 0.7 |

### Re-marking effect (signal on minus off, paired by episode)

| venue | leader | ΔP&L entry tier | ΔP&L top tier | Δ adverse selection 60 s |
|---|---|---|---|---|
| Binance BTCUSDT | coinbase | -0.98 [-1.10, -0.78] | -0.42 [-0.92, -0.19] | +0.18 [-0.02, +0.53] |
| Coinbase BTC-USD | binance | -0.56 [-0.98, -0.30] | +0.12 [+0.07, +0.26] | -0.31 [-0.61, -0.16] |
| Bitstamp BTC/USD | coinbase | -4.54 [-6.31, +1.46] | -1.27 [-1.39, -1.00] | +0.87 [-0.27, +9.54] |

## Attribution per fill (bp; base configuration, own mid)

| venue | tier | spread capture | − adverse selection (60 s) | − inventory (hold to episode end + flattening) | − fee | = P&L | identity gap (USD) |
|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | Regular user / VIP 0 | 0.38 [0.36, 0.39] | 2.16 [2.00, 2.26] | 0.09 [-0.07, 0.34] | 10.0 | -11.87 [-11.98, -11.80] | 7.11e-15 |
| Binance BTCUSDT | VIP 9 | 0.38 [0.36, 0.39] | 2.16 [2.00, 2.26] | -0.07 [-0.20, 0.13] | 1.1 | -2.81 [-2.88, -2.77] | 1.78e-15 |
| Coinbase BTC-USD | $0K-$10K | 0.22 [0.13, 0.27] | 0.95 [0.87, 1.10] | 0.16 [-0.14, 0.79] | 40.0 | -40.88 [-41.77, -40.46] | 5.68e-14 |
| Coinbase BTC-USD | $400M+ | 0.22 [0.13, 0.27] | 0.95 [0.87, 1.10] | -0.13 [-0.14, -0.10] | 0.0 | -0.60 [-0.88, -0.46] | 8.88e-16 |
| Bitstamp BTC/USD | < $10K | -0.37 [-0.47, -0.13] | 0.80 [0.61, 0.97] | 1.36 [0.97, 2.27] | 30.0 | -32.65 [-33.95, -32.10] | 3.22e+00 |
| Bitstamp BTC/USD | $1B+ | -0.37 [-0.47, -0.13] | 0.80 [0.61, 0.97] | -0.12 [-0.20, -0.09] | 0.0 | -1.17 [-1.48, -1.04] | 2.42e-01 |

## Mark-outs of the fills (bp, positive = the fill made money against the later mid)

| venue | signal | 1 s | 10 s | 60 s | fill reasons |
|---|---|---|---|---|---|
| Binance BTCUSDT | off | -0.79 [-0.86, -0.74] | -1.74 [-2.21, -1.43] | -1.78 [-1.87, -1.65] | queue 92, through 82, cross 5 |
| Binance BTCUSDT | on | -0.89 [-1.11, -0.78] | -1.33 [-1.54, -1.23] | -1.96 [-2.17, -1.86] | queue 53, through 52, cross 2 |
| Coinbase BTC-USD | off | -0.48 [-0.59, -0.44] | -0.56 [-0.99, -0.36] | -0.72 [-0.98, -0.61] | through 98, cross 98, queue 15 |
| Coinbase BTC-USD | on | -0.66 [-0.93, -0.53] | -0.67 [-1.31, -0.34] | -0.49 [-0.51, -0.44] | cross 124, through 101, queue 15 |
| Bitstamp BTC/USD | off | -0.93 [-1.06, -0.60] | -1.06 [-1.35, -0.71] | -1.18 [-1.41, -0.74] | cross 107, queue 16, through 15 |
| Bitstamp BTC/USD | on | -0.62 [-0.88, -0.52] | -0.90 [-1.53, -0.65] | -1.97 [-10.37, -0.78] | cross 37, queue 5, through 4 |

## Sensitivity (top tier P&L per fill, bp; own mid unless stated)

| venue | configuration | fills | P&L top, signal off | P&L top, signal on |
|---|---|---|---|---|
| Binance BTCUSDT | latency 50 ms, naive_fifo, c_delta 0.5 | 179 | -2.81 [-2.88, -2.77] | -3.23 [-3.80, -2.96] |
| Coinbase BTC-USD | latency 50 ms, naive_fifo, c_delta 0.5 | 211 | -0.60 [-0.88, -0.46] | -0.47 [-0.62, -0.40] |
| Bitstamp BTC/USD | latency 50 ms, naive_fifo, c_delta 0.5 | 138 | -1.17 [-1.48, -1.04] | -2.44 [-2.48, -2.43] |

## Lead-lag between the venues' mids (Hayashi-Yoshida; theta* > 0: the first venue leads; grid ±2000 ms step 20 ms; 5-minute blocks)

| pair | clock | theta* (ms) [95 %] | LLR [95 %] | rho* | rho(0) | P(first leads) | blocks | mid changes |
|---|---|---|---|---|---|---|---|---|
| binance vs coinbase | exchange | -40 [-40, 0] | 0.57 [0.53, 0.60] | 0.954 | 0.945 | 0.00 | 3 | 495 / 2,299 |
| binance vs coinbase | receive | -120 [-120, -45] | 0.53 [0.51, 0.56] | 0.969 | 0.892 | 0.00 | 3 | 495 / 2,181 |
| binance vs coinbase | bookticker | -40 [-200, -20] | 0.27 [0.22, 0.34] | 0.744 | 0.714 | 0.00 | 3 | 525 / 2,181 |
| binance vs bitstamp | exchange | 140 [100, 237] | 1.63 [1.34, 1.80] | 0.821 | 0.583 | 1.00 | 3 | 495 / 3,684 |
| binance vs bitstamp | receive | 80 [-260, 160] | 0.84 [0.70, 0.94] | 1.076 | 1.006 | 0.72 | 3 | 495 / 1,597 |
| binance vs bitstamp | bookticker | 20 [-280, 260] | 0.54 [0.46, 0.57] | 0.922 | 0.898 | 0.94 | 3 | 525 / 1,597 |
| coinbase vs bitstamp | exchange | 120 [80, 180] | 3.10 [2.39, 3.87] | 0.591 | 0.434 | 1.00 | 3 | 2,299 / 3,684 |
| coinbase vs bitstamp | receive | 180 [60, 412] | 1.41 [1.20, 1.81] | 0.791 | 0.710 | 1.00 | 3 | 2,181 / 1,597 |

Leader used by the re-marking signal (largest LLR against the venue, exchange clock): binance ← coinbase, coinbase ← binance, bitstamp ← coinbase.

Cross-venue mid difference on a 1-second grid (bp): binance - coinbase: mean 4.6, sd 0.7, 5–95 % [3.4, 5.8]; binance - bitstamp: mean 4.4, sd 0.6, 5–95 % [3.5, 5.5]; coinbase - bitstamp: mean -0.3, sd 0.9, 5–95 % [-1.7, 1.2].

Quoter parameters: {"lot": 0.01, "c_delta": 0.5, "c_q": 0.25, "T": 10.0, "requote_tol_bp": 0.25, "max_inventory": 5, "decision_ms": 100, "vol_halflife_s": 120.0, "sigma0_bp": 0.5, "basis_halflife_s": 600.0, "episode_s": 900.0, "signal": 0, "latency_ms": 50}
