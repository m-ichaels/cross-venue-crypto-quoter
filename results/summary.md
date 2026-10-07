# cross-venue-crypto-quoter — run summary (built 2026-10-07T20:39:32Z)

## Recording

| venue | hour files | raw lines | raw MB (gzip) | depth msgs | trades | gaps | resyncs | notes |
|---|---|---|---|---|---|---|---|---|
| binance | 6 (2026-10-07T15 .. 2026-10-07T20) | 684,043 | 27.8 | 646,909 | 2,308,047 | 5 | 11 |  |
| coinbase | 6 (2026-10-07T15 .. 2026-10-07T20) | 359,816 | 32.3 | 1,044,438 | 378,074 | 0 | 14 |  |
| bitstamp | 6 (2026-10-07T15 .. 2026-10-07T20) | 3,193,574 | 98.0 | 13,305,537 | 41,974 | 0 | 44 | L3 orders; unknown deletes 583; crossed-book messages skipped 3214515 |
| binance_bbo | 6 (2026-10-07T15 .. 2026-10-07T20) | 1,604,736 | 16.6 | 6,965,410 | 0 | 0 | 0 |  |

## P&L per fill (bp of notional; base: latency 50 ms, queue model naive_fifo, c_delta 0.5; 95 % intervals from resampling 15-minute episodes)

| venue | signal | fills | fills / h | entry tier | P&L entry | top tier | P&L top | mark-out 60 s | median age (s) |
|---|---|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | own mid | 2277 | 455 | Regular user / VIP 0 (10.0 bp) | -11.57 [-11.74, -11.42] | VIP 9 (1.1 bp) | -2.51 [-2.66, -2.38] | -1.33 [-1.56, -1.13] | 2.4 |
| Binance BTCUSDT | re-marked off coinbase | 1103 | 220 | Regular user / VIP 0 (10.0 bp) | -11.89 [-12.35, -11.52] | VIP 9 (1.1 bp) | -2.66 [-3.02, -2.34] | -1.31 [-1.59, -1.07] | 2.1 |
| Coinbase BTC-USD | own mid | 2467 | 493 | $0K-$10K (40.0 bp) | -40.86 [-41.04, -40.68] | $400M+ (0.0 bp) | -0.49 [-0.57, -0.40] | -0.47 [-0.56, -0.38] | 1.2 |
| Coinbase BTC-USD | re-marked off binance | 3005 | 600 | $0K-$10K (40.0 bp) | -41.06 [-41.36, -40.78] | $400M+ (0.0 bp) | -0.44 [-0.55, -0.33] | -0.33 [-0.44, -0.22] | 1.4 |
| Bitstamp BTC/USD | own mid | 1223 | 264 | < $10K (30.0 bp) | -32.36 [-33.20, -31.78] | $1B+ (0.0 bp) | -1.15 [-1.31, -1.02] | -1.03 [-1.22, -0.87] | 2.4 |
| Bitstamp BTC/USD | re-marked off coinbase | 391 | 85 | < $10K (30.0 bp) | -34.78 [-37.98, -32.71] | $1B+ (0.0 bp) | -1.02 [-2.34, -0.06] | -0.18 [-0.55, 0.33] | 0.9 |

### Re-marking effect (signal on minus off, paired by episode)

| venue | leader | ΔP&L entry tier | ΔP&L top tier | Δ adverse selection 60 s |
|---|---|---|---|---|
| Binance BTCUSDT | coinbase | -0.33 [-0.72, -0.00] | -0.14 [-0.47, +0.15] | +0.11 [-0.12, +0.36] |
| Coinbase BTC-USD | binance | -0.20 [-0.42, +0.01] | +0.05 [-0.02, +0.12] | -0.25 [-0.31, -0.18] |
| Bitstamp BTC/USD | coinbase | -2.41 [-5.35, -0.44] | +0.14 [-1.08, +1.02] | -0.59 [-0.90, -0.34] |

## Attribution per fill (bp; base configuration, own mid)

| venue | tier | spread capture | − adverse selection (60 s) | − inventory (hold to episode end + flattening) | − fee | = P&L | identity gap (USD) |
|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | Regular user / VIP 0 | 0.32 [0.28, 0.35] | 1.65 [1.45, 1.88] | 0.24 [0.04, 0.43] | 10.0 | -11.57 [-11.74, -11.42] | 1.42e-14 |
| Binance BTCUSDT | VIP 9 | 0.32 [0.28, 0.35] | 1.65 [1.45, 1.88] | 0.08 [-0.11, 0.26] | 1.1 | -2.51 [-2.66, -2.38] | 1.07e-14 |
| Coinbase BTC-USD | $0K-$10K | 0.42 [0.37, 0.48] | 0.90 [0.81, 0.99] | 0.39 [0.25, 0.52] | 40.0 | -40.86 [-41.04, -40.68] | 1.14e-13 |
| Coinbase BTC-USD | $400M+ | 0.42 [0.37, 0.48] | 0.90 [0.81, 0.99] | 0.02 [-0.04, 0.08] | 0.0 | -0.49 [-0.57, -0.40] | 1.15e-14 |
| Bitstamp BTC/USD | < $10K | 0.03 [-0.01, 0.07] | 1.06 [0.90, 1.24] | 1.33 [0.80, 2.10] | 30.0 | -32.36 [-33.20, -31.78] | 5.68e-14 |
| Bitstamp BTC/USD | $1B+ | 0.03 [-0.01, 0.07] | 1.06 [0.90, 1.24] | 0.12 [-0.06, 0.29] | 0.0 | -1.15 [-1.31, -1.02] | 7.11e-15 |

## Mark-outs of the fills (bp, positive = the fill made money against the later mid)

| venue | signal | 1 s | 10 s | 60 s | fill reasons |
|---|---|---|---|---|---|
| Binance BTCUSDT | off | -0.73 [-0.82, -0.64] | -1.19 [-1.34, -1.05] | -1.33 [-1.56, -1.13] | queue 1157, through 1036, cross 84 |
| Binance BTCUSDT | on | -0.82 [-0.96, -0.70] | -1.18 [-1.36, -1.02] | -1.31 [-1.59, -1.07] | through 555, queue 512, cross 36 |
| Coinbase BTC-USD | off | -0.46 [-0.52, -0.39] | -0.46 [-0.55, -0.37] | -0.47 [-0.56, -0.38] | cross 1254, through 1030, queue 183 |
| Coinbase BTC-USD | on | -0.43 [-0.51, -0.36] | -0.47 [-0.57, -0.38] | -0.33 [-0.44, -0.22] | cross 1497, through 1109, queue 399 |
| Bitstamp BTC/USD | off | -0.82 [-0.89, -0.76] | -0.99 [-1.12, -0.89] | -1.03 [-1.22, -0.87] | cross 802, through 252, queue 169 |
| Bitstamp BTC/USD | on | -0.36 [-0.64, 0.08] | -0.38 [-0.70, 0.08] | -0.18 [-0.55, 0.33] | cross 285, through 74, queue 32 |

## Sensitivity (top tier P&L per fill, bp; own mid unless stated)

| venue | configuration | fills | P&L top, signal off | P&L top, signal on |
|---|---|---|---|---|
| Binance BTCUSDT | latency 50 ms, naive_fifo, c_delta 0.25 | 4621 | -2.47 [-2.60, -2.35] | -2.59 [-2.82, -2.38] |
| Binance BTCUSDT | latency 0 ms, naive_fifo, c_delta 0.5 | 2549 | -2.47 [-2.61, -2.35] | -2.58 [-3.03, -2.20] |
| Binance BTCUSDT | latency 50 ms, naive_fifo, c_delta 0.5 | 2277 | -2.51 [-2.66, -2.38] | -2.66 [-3.02, -2.34] |
| Binance BTCUSDT | latency 50 ms, power_prob, c_delta 0.5 | 1861 | -2.30 [-2.45, -2.17] | -1.73 [-1.99, -1.49] |
| Binance BTCUSDT | latency 50 ms, risk_averse, c_delta 0.5 | 2644 | -2.51 [-2.66, -2.36] | -2.66 [-3.02, -2.36] |
| Binance BTCUSDT | latency 200 ms, naive_fifo, c_delta 0.5 | 2416 | -2.47 [-2.62, -2.34] | -2.61 [-2.94, -2.33] |
| Binance BTCUSDT | latency 50 ms, naive_fifo, c_delta 1 | 498 | -2.53 [-2.83, -2.26] | -3.00 [-3.74, -2.41] |
| Binance BTCUSDT | latency 50 ms, naive_fifo, c_delta 2 | 88 | -1.83 [-4.00, -0.04] | -2.32 [-5.68, 0.80] |
| Coinbase BTC-USD | latency 50 ms, naive_fifo, c_delta 0.25 | 5592 | -0.51 [-0.56, -0.47] | -0.49 [-0.56, -0.41] |
| Coinbase BTC-USD | latency 0 ms, naive_fifo, c_delta 0.5 | 2184 | -0.51 [-0.59, -0.42] | -0.44 [-0.55, -0.34] |
| Coinbase BTC-USD | latency 50 ms, naive_fifo, c_delta 0.5 | 2467 | -0.49 [-0.57, -0.40] | -0.44 [-0.55, -0.33] |
| Coinbase BTC-USD | latency 50 ms, power_prob, c_delta 0.5 | 2468 | -0.48 [-0.56, -0.39] | -0.41 [-0.52, -0.30] |
| Coinbase BTC-USD | latency 50 ms, risk_averse, c_delta 0.5 | 2463 | -0.49 [-0.57, -0.40] | -0.44 [-0.55, -0.34] |
| Coinbase BTC-USD | latency 200 ms, naive_fifo, c_delta 0.5 | 2430 | -0.52 [-0.63, -0.39] | -0.43 [-0.57, -0.30] |
| Coinbase BTC-USD | latency 50 ms, naive_fifo, c_delta 1 | 570 | -0.42 [-0.69, -0.15] | -0.22 [-0.49, 0.10] |
| Coinbase BTC-USD | latency 50 ms, naive_fifo, c_delta 2 | 78 | -0.82 [-3.19, 1.36] | 0.19 [-2.11, 2.15] |
| Bitstamp BTC/USD | latency 50 ms, naive_fifo, c_delta 0.25 | 1800 | -1.23 [-1.42, -1.07] | -1.05 [-1.76, -0.52] |
| Bitstamp BTC/USD | latency 0 ms, naive_fifo, c_delta 0.5 | 880 | -1.03 [-1.19, -0.86] | -0.19 [-1.47, 0.71] |
| Bitstamp BTC/USD | latency 50 ms, l3_exact, c_delta 0.5 | 1145 | -1.17 [-1.32, -1.04] | -1.08 [-2.49, -0.08] |
| Bitstamp BTC/USD | latency 50 ms, naive_fifo, c_delta 0.5 | 1223 | -1.15 [-1.31, -1.02] | -1.02 [-2.34, -0.06] |
| Bitstamp BTC/USD | latency 50 ms, power_prob, c_delta 0.5 | 1213 | -1.15 [-1.31, -1.02] | -1.10 [-2.53, -0.13] |
| Bitstamp BTC/USD | latency 50 ms, risk_averse, c_delta 0.5 | 1125 | -1.16 [-1.32, -1.03] | -1.03 [-2.35, -0.06] |
| Bitstamp BTC/USD | latency 200 ms, naive_fifo, c_delta 0.5 | 1167 | -1.30 [-1.58, -1.06] | -1.43 [-2.43, -0.69] |
| Bitstamp BTC/USD | latency 50 ms, naive_fifo, c_delta 1 | 453 | -0.96 [-1.26, -0.67] | -1.37 [-5.14, 1.03] |
| Bitstamp BTC/USD | latency 50 ms, naive_fifo, c_delta 2 | 81 | -0.28 [-2.19, 1.07] | -3.69 [-16.96, 4.97] |

## Lead-lag between the venues' mids (Hayashi-Yoshida; theta* > 0: the first venue leads; grid ±2000 ms step 20 ms; 10-minute blocks)

| pair | clock | theta* (ms) [95 %] | LLR [95 %] | rho* | rho(0) | P(first leads) | blocks | mid changes |
|---|---|---|---|---|---|---|---|---|
| binance vs coinbase | exchange | 0 [0, 40] | 0.88 [0.74, 1.05] | 0.947 | 0.947 | 0.22 | 27 | 4,744 / 24,527 |
| binance vs coinbase | receive | -40 [-120, -20] | 0.78 [0.66, 0.92] | 0.878 | 0.842 | 0.00 | 27 | 4,693 / 23,775 |
| binance vs coinbase | bookticker | -140 [-220, -20] | 0.45 [0.39, 0.52] | 0.817 | 0.768 | 0.00 | 27 | 7,248 / 23,775 |
| binance vs bitstamp | exchange | 180 [140, 320] | 1.75 [1.48, 2.14] | 0.932 | 0.732 | 1.00 | 25 | 4,744 / 20,978 |
| binance vs bitstamp | receive | 140 [20, 420] | 1.00 [0.83, 1.21] | 0.991 | 0.940 | 1.00 | 25 | 4,693 / 7,921 |
| binance vs bitstamp | bookticker | 100 [-20, 180] | 0.72 [0.60, 0.83] | 1.017 | 0.991 | 0.93 | 25 | 7,248 / 7,921 |
| coinbase vs bitstamp | exchange | 120 [120, 300] | 2.01 [1.66, 2.40] | 0.648 | 0.541 | 1.00 | 25 | 24,527 / 20,978 |
| coinbase vs bitstamp | receive | 400 [170, 640] | 1.32 [1.12, 1.56] | 0.766 | 0.706 | 1.00 | 25 | 23,775 / 7,921 |

Leader used by the re-marking signal (largest LLR against the venue, exchange clock): binance ← coinbase, coinbase ← binance, bitstamp ← coinbase.

Cross-venue mid difference on a 1-second grid (bp): binance - coinbase: mean 5.8, sd 1.2, 5–95 % [4.0, 7.8]; binance - bitstamp: mean 4.5, sd 4.4, 5–95 % [-8.7, 7.5]; coinbase - bitstamp: mean -1.3, sd 4.1, 5–95 % [-13.4, 1.4].

Quoter parameters: {"lot": 0.01, "c_delta": 0.5, "c_q": 0.25, "T": 10.0, "requote_tol_bp": 0.25, "max_inventory": 5, "decision_ms": 100, "vol_halflife_s": 120.0, "sigma0_bp": 0.5, "basis_halflife_s": 600.0, "episode_s": 900.0, "signal": 0, "latency_ms": 50}
