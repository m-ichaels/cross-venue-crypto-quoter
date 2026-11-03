# cross-venue-crypto-quoter: method and full results

The summary is in the [README](../README.md). This document has the method, the data and every table; like the README, `scripts/readme.py` generates it from the committed results.

**Question.** A crypto market maker quotes the same coin on several exchanges at once. On the Binance, Coinbase and Bitstamp BTC spot books, what does a one-lot inventory-skewed passive quoter earn per fill once spread capture, adverse selection, inventory and the venue's maker fee are all charged — at the entry fee tier and at the top tier — and does re-marking the quote off the venue that leads add anything?

**Answer (§Results; one recording session on one day, 2026-10-07, 5.0 h).** Replayed with queue-position fills on 5.0 hours of self-recorded order books, the quoter (0.01 BTC per order, half spread and inventory skew set by the mid's short-horizon volatility, quotes pulled after 10 s) is paid for with its fills, not by them:
- *By tier.* At the entry maker tier every venue loses money per fill — Binance VIP 0 (10 bp) **-11.57 [-11.74, -11.42] bp**, Coinbase $0K-$10K (40 bp) **-40.86 [-41.04, -40.68] bp**, Bitstamp < $10K (30 bp) **-32.36 [-33.20, -31.78] bp** — because the fee alone is an order of magnitude larger than the half spread these books offer. At the top maker tier the quoter nets -2.51 [-2.66, -2.38] bp per fill on Binance (VIP 9, 1.1 bp), nets -0.49 [-0.57, -0.40] bp on Coinbase ($400M+, 0 bp) and nets -1.15 [-1.31, -1.02] bp on Bitstamp ($1B+, 0 bp); 95 % intervals are from resampling the 20 15-minute episodes.
- *Why.* The fills are adversely selected on every venue: the 60 s mark-out of a fill is -1.33 [-1.56, -1.13] bp on Binance, -0.47 [-0.56, -0.38] on Coinbase and -1.03 [-1.22, -0.87] on Bitstamp, against spread capture of 0.32 [0.28, 0.35] / 0.42 [0.37, 0.48] / 0.03 [-0.01, 0.07] bp. 49 % of the Binance fills (93 % Coinbase, 86 % Bitstamp) come from the price running through the resting quote rather than from the queue draining; the choice of queue-position model moves the top-tier figure by at most 0.21 bp on Binance, 0.01 bp on Coinbase, 0.02 bp on Bitstamp.
- *Lead-lag.* With each exchange's own clock, Binance and Coinbase are not separable (LLR 0.88 [0.74, 1.05]; θ* = +0 ms [+0, +40], positive meaning Binance first); Binance leads Bitstamp (LLR 1.75 [1.48, 2.14]; θ* = +180 ms [+140, +320], positive meaning Binance first); Coinbase leads Bitstamp (LLR 2.01 [1.66, 2.40]; θ* = +120 ms [+120, +300], positive meaning Coinbase first). In receive time at the recorder (London) Coinbase leads Binance (LLR 0.78 [0.66, 0.92]; θ* = -40 ms [-120, -20], positive meaning Binance first); Binance and Bitstamp are not separable (LLR 1.00 [0.83, 1.21]; θ* = +140 ms [+20, +420], positive meaning Binance first); Coinbase leads Bitstamp (LLR 1.32 [1.12, 1.56]; θ* = +400 ms [+170, +640], positive meaning Coinbase first). Binance's depth feed is batched every 100 ms and Coinbase's every 50 ms, so leads below those scales are not resolvable here.
- *Re-marking.* Quoting off the leading venue's mid (re-based by the trailing cross-venue basis) changes nothing measurable (+0.05 [-0.02, +0.12] bp) per fill on Coinbase (reference Binance), changes nothing measurable (+0.14 [-1.08, +1.02] bp) on Bitstamp (reference Coinbase) and changes nothing measurable (-0.14 [-0.47, +0.15] bp) on Binance (reference Coinbase), paired by episode at the top tier; the full table is in §Results.

Data recorded 2026-10-07 by `cvq/recorder.py` from the venues' public websockets (175 MB gzip, 5,842,169 messages, no key, nothing bought); fee schedules read the same day (`data/fees/README.md`). Python package `cvq`, 25 tests; CI runs the tests and re-renders the summary, the README and this document from the committed results. Nothing is simulated except the known-answer tests.

---

## Layout

```
cvq/recorder.py        the live recorder: Binance depth@100ms + trade (+ bookTicker) with the REST snapshot and the U/u rule,
                       Coinbase level2_batch + matches, Bitstamp live_orders + live_trades (L3) with the group=2 snapshot;
                       gzip NDJSON per hour, stop file, reconnect with backoff
cvq/raw.py, books.py   torn-tail-tolerant reader; per-venue book rebuilders -> hourly msgs / l2 / trades / bbo / l3 parquet,
                       every hour file opening with a full-book reset
cvq/vendor/queue_model.py  the three L2 queue-position models (naive FIFO, power-probability, risk-averse), ported from
                       the owner's lob-execution-sim (hftbacktest's rules), assumptions stated in the module
cvq/vendor/leadlag.py  Hayashi-Yoshida contrast with a shift, HRV theta*, Huth-Abergel LLR, block bootstrap (from delta-one-basis)
cvq/quoter.py          the Avellaneda-Stoikov / GLFT stationary quoter in bp of the mid: reservation price, half spread,
                       inventory skew, post-only clamp, EWMA volatility and cross-venue basis
cvq/replay.py          the event-time replay: decision clock, latency both ways, queue / through / cross / depth fill rules,
                       the Bitstamp order-id exact queue, episodes flattened at the far touch
cvq/pnl.py             mark-outs, the four-term attribution (an exact identity), notional-weighted episode bootstrap
scripts/               build_books, run_leadlag, run_replay, plots, summarize, readme (README.md and docs/method.md from the two templates), run_all.sh
configs/fees.json      the two maker tiers per venue with sources;  data/fees/  the evidence saved on the day
tests/                 25 tests;  results/  replay.json, leadlag.json, books.json, summary.md;  figures/  png
data/raw/ (ignored)    the recording;  data/derived/ (ignored)  the hourly tables;  data/fills/  one fills table per pass
```

Install: `pip install -e .[test]`; `python -m pytest`; `scripts/run_all.sh [--quick]` (books → lead-lag → replay → figures → summary → README → tests; about 220 s for the 50 replay passes on the full recording). The README and this document are generated from `scripts/README.template.md` and `scripts/METHOD.template.md` by `scripts/readme.py`, so every number is the run's.

---

## Data

| venue | instrument, streams | hours | raw MB (gzip) | depth messages | trades | gaps / resyncs | notes |
|---|---|---|---|---|---|---|---|
| Binance spot | BTCUSDT `depth@100ms` + `trade`, REST snapshot (5000 levels) | 6 | 28 | 646,909 | 2,308,047 | 5 / 11 | tick $0.01; 114,595 top-of-book changes at 100 ms resolution |
| Binance spot | BTCUSDT `bookTicker` | 6 | 17 | 6,965,410 | — | — | real-time best bid/ask, receive time only; used for the lead-lag check |
| Coinbase Exchange | BTC-USD `level2_batch` (50 ms) + `matches` | 6 | 32 | 1,044,438 | 378,074 | 0 / 14 | 93,086 top-of-book changes; `level2` and `full` need an API key since 2023 |
| Bitstamp | BTC/USD `live_orders` + `live_trades` (order by order), REST `group=2` snapshot | 6 | 98 | 13,305,537 | 41,974 | 0 / 44 | order ids: the exact queue; 112,352 top-of-book changes; 583 deletes of unseen orders |

| venue | hour files | raw lines | raw MB (gzip) | depth msgs | trades | gaps | resyncs | notes |
|---|---|---|---|---|---|---|---|---|
| binance | 6 (2026-10-07T15 .. 2026-10-07T20) | 684,043 | 27.8 | 646,909 | 2,308,047 | 5 | 11 |  |
| coinbase | 6 (2026-10-07T15 .. 2026-10-07T20) | 359,816 | 32.3 | 1,044,438 | 378,074 | 0 | 14 |  |
| bitstamp | 6 (2026-10-07T15 .. 2026-10-07T20) | 3,193,574 | 98.0 | 13,305,537 | 41,974 | 0 | 44 | L3 orders; unknown deletes 583; crossed-book messages skipped 3214515 |
| binance_bbo | 6 (2026-10-07T15 .. 2026-10-07T20) | 1,604,736 | 16.6 | 6,965,410 | 0 | 0 | 0 |  |

Recorded from a laptop in London; receive-minus-exchange time (network delay plus local clock offset) ran about 260 ms for Binance, 200 ms for Coinbase and 180–250 ms for Bitstamp (`recorder.log`). Formats, endpoints and the regeneration command: `data/SOURCES.md`. Cross-venue mid differences on a 1-second grid (bp of the second venue's mid): Binance − Coinbase 5.8 (sd 1.2), Binance − Bitstamp 4.5 (sd 4.4), Coinbase − Bitstamp -1.3 (sd 4.1) — the USDT/USD and venue bases the re-marking signal has to remove.

**Fees** (`configs/fees.json`, read 2026-10-07): Binance VIP 0 maker 10 bp (Binance's own support article) and VIP 9 maker 1.1 bp; Coinbase Exchange $0K-$10K maker 40 bp and $400M+ maker 0 bp (Coinbase's help page); Bitstamp < $10K maker 30 bp and $1B+ maker 0 bp. Binance's and Bitstamp's own fee pages could not be read by script on the day (JavaScript shell; bot wall) and those figures come from third-party reproductions dated 2026, named in `data/fees/README.md`. The same tier's taker fee is charged on the end-of-episode flattening trade.

---

## Method

**Books.** Binance diffs are synchronised to the REST snapshot with the documented rule (drop `u ≤ lastUpdateId`, first event spans `lastUpdateId + 1`, then `U = previous u + 1`; a gap invalidates the book until the next snapshot in the stream). Coinbase `l2update` sizes are absolute. Bitstamp's L2 is the per-price aggregate of the order map, with per-level order counts so that a float residue cannot keep a dead level alive; events received before the snapshot but newer than its microtimestamp are replayed onto it. Every hour file starts with a full-book reset so a replay can begin anywhere. Prices sit on a $0.01 grid on all three venues and are compared as integer ticks.

**Quoter** (`cvq/quoter.py`; Avellaneda–Stoikov 2008 in the stationary GLFT form, written in bp of the mid with the risk term through the mid's volatility rather than through (γ, k), which one session cannot identify):

$$r_t = m_{\text{ref},t}\Big(1 - \frac{q_t\,\kappa_t}{10^4}\Big),\qquad \kappa_t = c_q\,\sigma_t\sqrt{T},\qquad \delta_t = \max\big(c_\delta\,\sigma_t\sqrt{T},\ \text{own half spread},\ 1\ \text{tick}\big),$$

bid at $r_t(1-\delta_t/10^4)$ rounded down to the tick and capped at best ask − 1 tick (post-only), ask symmetric; $q_t$ the inventory in lots, $\sigma_t$ the EWMA volatility of the 1-second log-mid change (half-life 120 s), $T$ = 10 s the stale-quote horizon: a resting order older than $T$ or more than 0.25 bp from its new target is pulled and re-quoted (and goes to the back of the queue); the side that would take $|q|$ beyond 5 lots is not quoted. Base parameters $c_\delta$ = 0.5, $c_q$ = 0.25, lot 0.01 BTC, decisions every 100 ms. $m_{\text{ref}}$ is the venue's own mid, or — the re-marking variant — the leading venue's mid less the EWMA (half-life 600 s) of the cross-venue mid difference. The leader is the other venue with the largest lead-lag ratio against this one: Binance is re-marked off Coinbase, Coinbase is re-marked off Binance, Bitstamp is re-marked off Coinbase.

**Replay** (`cvq/replay.py`). Event time is the exchange's own timestamp. A decision at $d$ sees the book and the leader's mid as of $d - L$ and its orders and cancels act at $d + L$ (one-way latency $L$ = 50 ms in the base case; 0 and 200 ms as sensitivities); fills that land before a cancel takes effect count. A resting order fills by four rules: *queue* — a trade at its price against its side consumes the queue ahead under the queue model and the excess executes against us; *through* — a trade against our side beyond our price (the taker swept our level first) fills us in full; *cross* — the opposite best moves to or through our price; *depth* — the level shrinks by more than the recorded trades and the estimated size behind us (hftbacktest's rule). On Bitstamp a fifth, model-free rule uses the order ids: a trade at our price whose maker was created after us would have hit us first under FIFO (`l3_exact`). Post-only orders that would cross on arrival are rejected and counted (500 / 610 / 404 of 8,727 / 16,505 / 7,566 placements). Inventory is flattened at the far touch at the end of every 15-minute episode and the quoter restarts flat; episodes are also the bootstrap unit. Replay has no market impact by construction: our orders are not in the recorded book, and nobody reacts to them.

**Queue position** (`cvq/vendor/queue_model.py`, hftbacktest's rules as reproduced in the owner's `lob-execution-sim`). Our order joins behind the visible size at its price; trades at the price consume the front; a decrease in the level beyond the recorded trades is a cancellation, allocated behind us with probability $f(\text{back})/(f(\text{back}) + f(\text{front}))$ — $f(x)=x$ (naive FIFO), $f(x)=x^3$ (power-probability), or all behind us (risk-averse). Assumptions, stated: FIFO at one price, no hidden liquidity, the recorded trades are matched against the queue ahead before reaching us. Against the Bitstamp order ids these models can be checked: the `l3_exact` row in the sensitivity table is the observation the three models approximate.

**P&L per fill** (`cvq/pnl.py`). For a fill of side $s$ at price $p$ with mid $m_0$ at the fill, $m_{60}$ sixty seconds later (capped at the episode end) and $m_T$ at the episode end, in bp of $p$:

$$\text{P\&L} = \underbrace{s\,(m_0 - p)}_{\text{spread capture}} - \underbrace{\big(-s\,(m_{60} - m_0)\big)}_{\text{adverse selection}} - \underbrace{\Big(-s\,(m_T - m_{60}) + \text{flattening share}\Big)}_{\text{inventory cost}} - \text{maker fee},$$

an identity: the four terms sum to the episode's realised P&L with positions marked at $m_T$, the residual inventory crossed at the far touch with the taker fee, and maker fees paid (the identity gap per tier is printed in `results/summary.md`; it is at machine precision). Reported figures are notional-weighted means over fills with 95 % intervals from resampling episodes with replacement (2,000 draws); the re-marking effect is the paired (same episodes) difference. Mark-outs at 1, 10 and 60 s are the same quantity without the fee and inventory terms.

**Lead-lag** (`cvq/vendor/leadlag.py`). For each pair of venues the Hayashi–Yoshida covariance of the two mid-change series with a shift $\theta$ on the second, over a ±2000 ms grid at 20 ms, normalised to $\rho(\theta)$; $\theta^* = \arg\max|\rho|$ (Hoffmann–Rosenbaum–Vetter) and the Huth–Abergel ratio $\text{LLR} = \sum_{\theta>0}\rho^2 / \sum_{\theta<0}\rho^2$ (> 1: the first venue leads), with 10-minute blocks as the bootstrap unit. Three clocks: each exchange's own timestamps (assumes their clocks agree), the recorder's receive time for both legs (one clock, but each leg carries its own network path), and Binance's real-time `bookTicker` against the others' receive time.

---

## Results

### P&L per fill by venue, tier and reference price

![pnl](../figures/pnl_by_tier.png)

*Figure 1. P&L per fill at the entry and top maker tiers, own-mid quoter (solid) and re-marked off the leading venue (hatched), with 95 % episode-bootstrap intervals. Base configuration: latency 50 ms, naive_fifo queue model.*

| venue | signal | fills | fills / h | entry tier | P&L entry | top tier | P&L top | mark-out 60 s | median age (s) |
|---|---|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | own mid | 2277 | 455 | Regular user / VIP 0 (10.0 bp) | -11.57 [-11.74, -11.42] | VIP 9 (1.1 bp) | -2.51 [-2.66, -2.38] | -1.33 [-1.56, -1.13] | 2.4 |
| Binance BTCUSDT | re-marked off coinbase | 1103 | 220 | Regular user / VIP 0 (10.0 bp) | -11.89 [-12.35, -11.52] | VIP 9 (1.1 bp) | -2.66 [-3.02, -2.34] | -1.31 [-1.59, -1.07] | 2.1 |
| Coinbase BTC-USD | own mid | 2467 | 493 | $0K-$10K (40.0 bp) | -40.86 [-41.04, -40.68] | $400M+ (0.0 bp) | -0.49 [-0.57, -0.40] | -0.47 [-0.56, -0.38] | 1.2 |
| Coinbase BTC-USD | re-marked off binance | 3005 | 600 | $0K-$10K (40.0 bp) | -41.06 [-41.36, -40.78] | $400M+ (0.0 bp) | -0.44 [-0.55, -0.33] | -0.33 [-0.44, -0.22] | 1.4 |
| Bitstamp BTC/USD | own mid | 1223 | 264 | < $10K (30.0 bp) | -32.36 [-33.20, -31.78] | $1B+ (0.0 bp) | -1.15 [-1.31, -1.02] | -1.03 [-1.22, -0.87] | 2.4 |
| Bitstamp BTC/USD | re-marked off coinbase | 391 | 85 | < $10K (30.0 bp) | -34.78 [-37.98, -32.71] | $1B+ (0.0 bp) | -1.02 [-2.34, -0.06] | -0.18 [-0.55, 0.33] | 0.9 |

| venue | leader | ΔP&L entry tier | ΔP&L top tier | Δ adverse selection 60 s |
|---|---|---|---|---|
| Binance BTCUSDT | coinbase | -0.33 [-0.72, -0.00] | -0.14 [-0.47, +0.15] | +0.11 [-0.12, +0.36] |
| Coinbase BTC-USD | binance | -0.20 [-0.42, +0.01] | +0.05 [-0.02, +0.12] | -0.25 [-0.31, -0.18] |
| Bitstamp BTC/USD | coinbase | -2.41 [-5.35, -0.44] | +0.14 [-1.08, +1.02] | -0.59 [-0.90, -0.34] |

### Where the fill's P&L goes

![attribution](../figures/attribution.png)

*Figure 2. The four terms of the per-fill P&L at the top maker tier, own mid. Costs are drawn negative; the horizontal line is the net.*

| venue | tier | spread capture | − adverse selection (60 s) | − inventory (hold to episode end + flattening) | − fee | = P&L | identity gap (USD) |
|---|---|---|---|---|---|---|---|
| Binance BTCUSDT | Regular user / VIP 0 | 0.32 [0.28, 0.35] | 1.65 [1.45, 1.88] | 0.24 [0.04, 0.43] | 10.0 | -11.57 [-11.74, -11.42] | 1.42e-14 |
| Binance BTCUSDT | VIP 9 | 0.32 [0.28, 0.35] | 1.65 [1.45, 1.88] | 0.08 [-0.11, 0.26] | 1.1 | -2.51 [-2.66, -2.38] | 1.07e-14 |
| Coinbase BTC-USD | $0K-$10K | 0.42 [0.37, 0.48] | 0.90 [0.81, 0.99] | 0.39 [0.25, 0.52] | 40.0 | -40.86 [-41.04, -40.68] | 1.14e-13 |
| Coinbase BTC-USD | $400M+ | 0.42 [0.37, 0.48] | 0.90 [0.81, 0.99] | 0.02 [-0.04, 0.08] | 0.0 | -0.49 [-0.57, -0.40] | 1.15e-14 |
| Bitstamp BTC/USD | < $10K | 0.03 [-0.01, 0.07] | 1.06 [0.90, 1.24] | 1.33 [0.80, 2.10] | 30.0 | -32.36 [-33.20, -31.78] | 5.68e-14 |
| Bitstamp BTC/USD | $1B+ | 0.03 [-0.01, 0.07] | 1.06 [0.90, 1.24] | 0.12 [-0.06, 0.29] | 0.0 | -1.15 [-1.31, -1.02] | 7.11e-15 |

![markouts](../figures/markouts.png)

*Figure 3. Mark-out of the fills at 1, 10 and 60 s (positive = the fill made money against the later mid), own mid (filled markers) and re-marked (open).*

| venue | signal | 1 s | 10 s | 60 s | fill reasons |
|---|---|---|---|---|---|
| Binance BTCUSDT | off | -0.73 [-0.82, -0.64] | -1.19 [-1.34, -1.05] | -1.33 [-1.56, -1.13] | queue 1157, through 1036, cross 84 |
| Binance BTCUSDT | on | -0.82 [-0.96, -0.70] | -1.18 [-1.36, -1.02] | -1.31 [-1.59, -1.07] | through 555, queue 512, cross 36 |
| Coinbase BTC-USD | off | -0.46 [-0.52, -0.39] | -0.46 [-0.55, -0.37] | -0.47 [-0.56, -0.38] | cross 1254, through 1030, queue 183 |
| Coinbase BTC-USD | on | -0.43 [-0.51, -0.36] | -0.47 [-0.57, -0.38] | -0.33 [-0.44, -0.22] | cross 1497, through 1109, queue 399 |
| Bitstamp BTC/USD | off | -0.82 [-0.89, -0.76] | -0.99 [-1.12, -0.89] | -1.03 [-1.22, -0.87] | cross 802, through 252, queue 169 |
| Bitstamp BTC/USD | on | -0.36 [-0.64, 0.08] | -0.38 [-0.70, 0.08] | -0.18 [-0.55, 0.33] | cross 285, through 74, queue 32 |

### Sensitivity: latency, queue model, half-spread multiplier

![sensitivity](../figures/sensitivity.png)

*Figure 4. Top-tier P&L per fill against one-way latency, under each queue-position model (Bitstamp also with the order-id exact queue), and against the half-spread multiplier $c_\delta$ (fills per hour above the bars).*

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

### Lead-lag

![leadlag](../figures/leadlag.png)

*Figure 5. The Hayashi–Yoshida contrast $\rho(\theta)$ per venue pair under the three clocks; the vertical line and label mark $\theta^*$ and the LLR on the exchange clock.*

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

![session](../figures/session.png)

*Figure 6. The three mids over the recording and the Coinbase and Bitstamp bases to Binance in bp.*

---

## Validation

- Queue models: trades consume the front and execute us past zero; arrivals never move us forward; a cancel is split by queue share (naive) or $x^3$ (power) and all behind us (risk-averse); recorded trades are not double-counted as cancels — worked examples of hftbacktest's rules.
- Books: Binance's snapshot rule on a constructed stream (drop, span, chain, gap); Coinbase absolute sizes and the maker-side convention; Bitstamp order aggregation with the snapshot replay, the order-id aggressor rule and an exactly-zero level after deletions; a torn gzip tail is read to the last complete line.
- Quoter: symmetric post-only quotes at flat inventory, downward skew when long, one side withdrawn at the bound, the half spread never tighter than the venue's or a tick, the EWMA volatility converging to the generating value.
- Replay and P&L: on a hand-made tape a sweep through the resting bid fills it at the right time, price and size, the episode flattens at the far touch, the mark-outs and the four attribution terms take their hand-computed values and sum to the realised P&L; latency delays the placement; the bootstrap recovers a known mean and a known paired difference.
- Lead-lag: the HY sum equals the realised covariance on synchronous data and the lagged cross-covariance for a whole-step shift; a known lag on Poisson-sampled Brownian motions is recovered and flips with the leg order; the block bootstrap covers the estimate.

## Limits, stated

- **One session on one day** (2026-10-07, 5.0 h, a London afternoon into the US session). The intervals are over episodes within that session and say nothing about other days, regimes or hours; the numbers are the method's output on this tape, not a forecast.
- The replay has no impact and no reaction: our quotes are invisible to the recorded participants, and the queue position on Binance and Coinbase is a model (three variants, all reported). The `through` and `cross` rules are optimistic for a maker (a sweep that reaches our price fills us in full) and the owner's earlier Bitstamp check found the L2 models over-estimate the queue ahead by about 20 %; the Bitstamp `l3_exact` row is the honest comparison and it is on one venue only.
- Clocks: exchange timestamps are assumed to agree with each other, the latency is symmetric, and Binance's mid is only observed every 100 ms (Coinbase's every 50 ms), which blurs the lead-lag and the re-marking signal at exactly the scale where it would matter most.
- The quoter is deliberately simple (one lot, volatility-scaled half spread and skew, fixed pull horizon) and its parameters were set a priori; the $c_\delta$ row shows how fast the answer moves with the width. No parameter was tuned to the tape.
- Fees: two of the three venue pages could not be machine-read on the day; those tiers are third-party reproductions dated 2026 and must be re-read before any use beyond this exercise. The BNB discount, rebates and liquidity-programme terms are not applied.
- One lot of 0.01 BTC is small on these books; nothing here scales to size.

## Reproduce

```
pip install -e .[test]
python -m pytest
python -m cvq.recorder --out data/raw --binance-bbo BTCUSDT --minutes 320     # or any length; STOP file to end early
scripts/run_all.sh                                                             # books, lead-lag, replay, figures, summary, README and docs/method.md
python scripts/run_replay.py --quick                                           # base configuration only
```

## References

- Avellaneda, M. and Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance* 8(3).
- Guéant, O., Lehalle, C.-A. and Fernandez-Tapia, J. (2013). Dealing with the inventory risk: a solution to the market making problem. *Mathematics and Financial Economics* 7. [arXiv:1105.3115](https://arxiv.org/abs/1105.3115)
- Hayashi, T. and Yoshida, N. (2005). On covariance estimation of non-synchronously observed diffusion processes. *Bernoulli* 11(2).
- Hoffmann, M., Rosenbaum, M. and Vetter, M. (2013). Estimation of the lead-lag parameter from non-synchronous data. *Bernoulli* 19(2). [arXiv:1011.1178](https://arxiv.org/abs/1011.1178)
- Huth, N. and Abergel, F. (2014). High frequency lead/lag relationships — empirical facts. *Journal of Empirical Finance* 26.
- Moallemi, C. and Yuan, K. (2016). A model for queue position valuation in a limit order book. Working paper.
- hftbacktest (github.com/nkaz001/hftbacktest), queue-position models; the owner's lob-execution-sim, from which the queue models and the recorder are adapted.

## CV bullet

- **Cross-venue passive quoter on Binance, Coinbase and Bitstamp BTC books** | Python, websockets, parquet | `cross-venue-crypto-quoter` — Recorded 5.0 h of three public order-book feeds (Bitstamp order by order), rebuilt the books, and replayed a one-lot inventory-skewed GLFT quoter with queue-position fills and latency: per fill the quoter nets -2.51 [-2.66, -2.38] bp on Binance at the VIP 9 maker tier, nets -0.49 [-0.57, -0.40] bp on Coinbase and nets -1.15 [-1.31, -1.02] bp on Bitstamp at their top tiers, and loses -11.57 [-11.74, -11.42] / -40.86 [-41.04, -40.68] / -32.36 [-33.20, -31.78] bp at the entry tiers, with the fee and the 60 s adverse selection attributed exactly; Hayashi–Yoshida lead-lag between the venues' mids on three clocks, and the re-marked variant changes nothing measurable (+0.05 [-0.02, +0.12] bp) on Coinbase and changes nothing measurable (+0.14 [-1.08, +1.02] bp) on Bitstamp.
