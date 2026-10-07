# cross-venue-crypto-quoter — what a one-lot passive quoter earns per fill on three BTC spot books, by maker-fee tier, and what re-marking off the leading venue adds

**Question.** A crypto market maker quotes the same coin on several exchanges at once. On the Binance, Coinbase and Bitstamp BTC spot books, what does a one-lot inventory-skewed passive quoter earn per fill once spread capture, adverse selection, inventory and the venue's maker fee are all charged — at the entry fee tier and at the top tier — and does re-marking the quote off the venue that leads add anything?

**Answer (§Results; one recording session on one day, {{rec_date}}, {{session_hours}} h).** Replayed with queue-position fills on {{session_hours}} hours of self-recorded order books, the quoter ({{lot_btc}} BTC per order, half spread and inventory skew set by the mid's short-horizon volatility, quotes pulled after {{prm_T}} s) is paid for with its fills, not by them:
- *By tier.* At the entry maker tier every venue loses money per fill — Binance VIP 0 ({{binance_entry_bp}} bp) **{{binance_entry_pnl_sig0}} bp**, Coinbase {{coinbase_entry_label}} ({{coinbase_entry_bp}} bp) **{{coinbase_entry_pnl_sig0}} bp**, Bitstamp {{bitstamp_entry_label}} ({{bitstamp_entry_bp}} bp) **{{bitstamp_entry_pnl_sig0}} bp** — because the fee alone is an order of magnitude larger than the half spread these books offer. At the top maker tier the quoter {{binance_top_word_sig0}} per fill on Binance (VIP 9, {{binance_top_bp}} bp), {{coinbase_top_word_sig0}} on Coinbase ({{coinbase_top_label}}, {{coinbase_top_bp}} bp) and {{bitstamp_top_word_sig0}} on Bitstamp ({{bitstamp_top_label}}, {{bitstamp_top_bp}} bp); 95 % intervals are from resampling the {{n_episodes}} {{episode_min}}-minute episodes.
- *Why.* The fills are adversely selected at every horizon: the 60 s mark-out of a fill is {{binance_mo60_sig0}} bp on Binance, {{coinbase_mo60_sig0}} on Coinbase and {{bitstamp_mo60_sig0}} on Bitstamp, against spread capture of {{binance_top_spread_sig0}} / {{coinbase_top_spread_sig0}} / {{bitstamp_top_spread_sig0}} bp. {{binance_share_through_cross_sig0}} % of the Binance fills ({{coinbase_share_through_cross_sig0}} % Coinbase, {{bitstamp_share_through_cross_sig0}} % Bitstamp) come from the price running through the resting quote rather than from the queue draining; {{qm_spread_sentence}}.
- *Lead-lag.* With each exchange's own clock, {{ll_verdict_exchange}}. In receive time at the recorder (London) {{ll_verdict_receive}}. Binance's depth feed is batched every 100 ms and Coinbase's every 50 ms, so leads below those scales are not resolvable here.
- *Re-marking.* Quoting off the leading venue's mid (re-based by the trailing cross-venue basis) {{coinbase_effect_top_word}} per fill on Coinbase (reference {{coinbase_leader}}), {{bitstamp_effect_top_word}} on Bitstamp (reference {{bitstamp_leader}}) and {{binance_effect_top_word}} on Binance (reference {{binance_leader}}), paired by episode at the top tier; the full table is in §Results.

Data recorded 2026-10-07 by `cvq/recorder.py` from the venues' public websockets ({{raw_mb_total}} MB gzip, {{raw_lines_total}} messages, no key, nothing bought); fee schedules read the same day (`data/fees/README.md`). Python package `cvq`, {{n_tests}} tests; CI runs the tests and re-renders the summary and this README from the committed results. Nothing is simulated except the known-answer tests.

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
scripts/               build_books, run_leadlag, run_replay, plots, summarize, readme, run_all.sh
configs/fees.json      the two maker tiers per venue with sources;  data/fees/  the evidence saved on the day
tests/                 {{n_tests}} tests;  results/  replay.json, leadlag.json, books.json, summary.md;  figures/  png
data/raw/ (ignored)    the recording;  data/derived/ (ignored)  the hourly tables;  data/fills/  one fills table per pass
```

Install: `pip install -e .[test]`; `python -m pytest`; `scripts/run_all.sh [--quick]` (books → lead-lag → replay → figures → summary → README → tests; about {{replay_seconds}} s for the {{n_passes}} replay passes on the full recording). The README is generated from `scripts/README.template.md` by `scripts/readme.py` so every number is the run's.

---

## Data

| venue | instrument, streams | hours | raw MB (gzip) | depth messages | trades | gaps / resyncs | notes |
|---|---|---|---|---|---|---|---|
| Binance spot | BTCUSDT `depth@100ms` + `trade`, REST snapshot (5000 levels) | {{n_hour_files}} | {{binance_raw_mb}} | {{binance_depth}} | {{binance_trades}} | {{binance_gaps}} / {{binance_resyncs}} | tick $0.01; {{binance_bbo_rows}} top-of-book changes at 100 ms resolution |
| Binance spot | BTCUSDT `bookTicker` | {{n_hour_files}} | {{binance_bbo_raw_mb}} | {{binance_bbo_depth}} | — | — | real-time best bid/ask, receive time only; used for the lead-lag check |
| Coinbase Exchange | BTC-USD `level2_batch` (50 ms) + `matches` | {{n_hour_files}} | {{coinbase_raw_mb}} | {{coinbase_depth}} | {{coinbase_trades}} | {{coinbase_gaps}} / {{coinbase_resyncs}} | {{coinbase_bbo_rows}} top-of-book changes; `level2` and `full` need an API key since 2023 |
| Bitstamp | BTC/USD `live_orders` + `live_trades` (order by order), REST `group=2` snapshot | {{n_hour_files}} | {{bitstamp_raw_mb}} | {{bitstamp_depth}} | {{bitstamp_trades}} | {{bitstamp_gaps}} / {{bitstamp_resyncs}} | order ids: the exact queue; {{bitstamp_bbo_rows}} top-of-book changes; {{bitstamp_unknown_deletes}} deletes of unseen orders |

{{table_recording}}

Recorded from a laptop in London; receive-minus-exchange time (network delay plus local clock offset) ran about 260 ms for Binance, 200 ms for Coinbase and 180–250 ms for Bitstamp (`recorder.log`). Formats, endpoints and the regeneration command: `data/SOURCES.md`. Cross-venue mid differences on a 1-second grid (bp of the second venue's mid): Binance − Coinbase {{basis_binance_coinbase_mean}} (sd {{basis_binance_coinbase_sd}}), Binance − Bitstamp {{basis_binance_bitstamp_mean}} (sd {{basis_binance_bitstamp_sd}}), Coinbase − Bitstamp {{basis_coinbase_bitstamp_mean}} (sd {{basis_coinbase_bitstamp_sd}}) — the USDT/USD and venue bases the re-marking signal has to remove.

**Fees** (`configs/fees.json`, read 2026-10-07): Binance VIP 0 maker {{binance_entry_bp}} bp (Binance's own support article) and VIP 9 maker {{binance_top_bp}} bp; Coinbase Exchange {{coinbase_entry_label}} maker {{coinbase_entry_bp}} bp and {{coinbase_top_label}} maker {{coinbase_top_bp}} bp (Coinbase's help page); Bitstamp {{bitstamp_entry_label}} maker {{bitstamp_entry_bp}} bp and {{bitstamp_top_label}} maker {{bitstamp_top_bp}} bp. Binance's and Bitstamp's own fee pages could not be read by script on the day (JavaScript shell; bot wall) and those figures come from third-party reproductions dated 2026, named in `data/fees/README.md`. The same tier's taker fee is charged on the end-of-episode flattening trade.

---

## Method

**Books.** Binance diffs are synchronised to the REST snapshot with the documented rule (drop `u ≤ lastUpdateId`, first event spans `lastUpdateId + 1`, then `U = previous u + 1`; a gap invalidates the book until the next snapshot in the stream). Coinbase `l2update` sizes are absolute. Bitstamp's L2 is the per-price aggregate of the order map, with per-level order counts so that a float residue cannot keep a dead level alive; events received before the snapshot but newer than its microtimestamp are replayed onto it. Every hour file starts with a full-book reset so a replay can begin anywhere. Prices sit on a $0.01 grid on all three venues and are compared as integer ticks.

**Quoter** (`cvq/quoter.py`; Avellaneda–Stoikov 2008 in the stationary GLFT form, written in bp of the mid with the risk term through the mid's volatility rather than through (γ, k), which one session cannot identify):

$$r_t = m_{\text{ref},t}\Big(1 - \frac{q_t\,\kappa_t}{10^4}\Big),\qquad \kappa_t = c_q\,\sigma_t\sqrt{T},\qquad \delta_t = \max\big(c_\delta\,\sigma_t\sqrt{T},\ \text{own half spread},\ 1\ \text{tick}\big),$$

bid at $r_t(1-\delta_t/10^4)$ rounded down to the tick and capped at best ask − 1 tick (post-only), ask symmetric; $q_t$ the inventory in lots, $\sigma_t$ the EWMA volatility of the 1-second log-mid change (half-life {{prm_vol_halflife_s}} s), $T$ = {{prm_T}} s the stale-quote horizon: a resting order older than $T$ or more than {{prm_requote_tol_bp}} bp from its new target is pulled and re-quoted (and goes to the back of the queue); the side that would take $|q|$ beyond {{prm_max_inventory}} lots is not quoted. Base parameters $c_\delta$ = {{prm_c_delta}}, $c_q$ = {{prm_c_q}}, lot {{lot_btc}} BTC, decisions every {{prm_decision_ms}} ms. $m_{\text{ref}}$ is the venue's own mid, or — the re-marking variant — the leading venue's mid less the EWMA (half-life {{prm_basis_halflife_s}} s) of the cross-venue mid difference. The leader is the other venue with the largest lead-lag ratio against this one: {{ll_leaders}}.

**Replay** (`cvq/replay.py`). Event time is the exchange's own timestamp. A decision at $d$ sees the book and the leader's mid as of $d - L$ and its orders and cancels act at $d + L$ (one-way latency $L$ = {{prm_latency_ms}} ms in the base case; 0 and 200 ms as sensitivities); fills that land before a cancel takes effect count. A resting order fills by four rules: *queue* — a trade at its price against its side consumes the queue ahead under the queue model and the excess executes against us; *through* — a trade against our side beyond our price (the taker swept our level first) fills us in full; *cross* — the opposite best moves to or through our price; *depth* — the level shrinks by more than the recorded trades and the estimated size behind us (hftbacktest's rule). On Bitstamp a fifth, model-free rule uses the order ids: a trade at our price whose maker was created after us would have hit us first under FIFO (`l3_exact`). Post-only orders that would cross on arrival are rejected and counted ({{binance_rejected_sig0}} / {{coinbase_rejected_sig0}} / {{bitstamp_rejected_sig0}} of {{binance_placed_sig0}} / {{coinbase_placed_sig0}} / {{bitstamp_placed_sig0}} placements). Inventory is flattened at the far touch at the end of every {{episode_min}}-minute episode and the quoter restarts flat; episodes are also the bootstrap unit. Replay has no market impact by construction: our orders are not in the recorded book, and nobody reacts to them.

**Queue position** (`cvq/vendor/queue_model.py`, hftbacktest's rules as reproduced in the owner's `lob-execution-sim`). Our order joins behind the visible size at its price; trades at the price consume the front; a decrease in the level beyond the recorded trades is a cancellation, allocated behind us with probability $f(\text{back})/(f(\text{back}) + f(\text{front}))$ — $f(x)=x$ (naive FIFO), $f(x)=x^3$ (power-probability), or all behind us (risk-averse). Assumptions, stated: FIFO at one price, no hidden liquidity, the recorded trades are matched against the queue ahead before reaching us. Against the Bitstamp order ids these models can be checked: the `l3_exact` row in the sensitivity table is the observation the three models approximate.

**P&L per fill** (`cvq/pnl.py`). For a fill of side $s$ at price $p$ with mid $m_0$ at the fill, $m_{60}$ sixty seconds later (capped at the episode end) and $m_T$ at the episode end, in bp of $p$:

$$\text{P\&L} = \underbrace{s\,(m_0 - p)}_{\text{spread capture}} - \underbrace{\big(-s\,(m_{60} - m_0)\big)}_{\text{adverse selection}} - \underbrace{\Big(-s\,(m_T - m_{60}) + \text{flattening share}\Big)}_{\text{inventory cost}} - \text{maker fee},$$

an identity: the four terms sum to the episode's realised P&L with positions marked at $m_T$, the residual inventory crossed at the far touch with the taker fee, and maker fees paid (the identity gap per tier is printed in `results/summary.md`; it is at machine precision). Reported figures are notional-weighted means over fills with 95 % intervals from resampling episodes with replacement (2,000 draws); the re-marking effect is the paired (same episodes) difference. Mark-outs at 1, 10 and 60 s are the same quantity without the fee and inventory terms.

**Lead-lag** (`cvq/vendor/leadlag.py`). For each pair of venues the Hayashi–Yoshida covariance of the two mid-change series with a shift $\theta$ on the second, over a ±{{ll_grid_ms}} ms grid at {{ll_step_ms}} ms, normalised to $\rho(\theta)$; $\theta^* = \arg\max|\rho|$ (Hoffmann–Rosenbaum–Vetter) and the Huth–Abergel ratio $\text{LLR} = \sum_{\theta>0}\rho^2 / \sum_{\theta<0}\rho^2$ (> 1: the first venue leads), with {{ll_block_min}}-minute blocks as the bootstrap unit. Three clocks: each exchange's own timestamps (assumes their clocks agree), the recorder's receive time for both legs (one clock, but each leg carries its own network path), and Binance's real-time `bookTicker` against the others' receive time.

---

## Results

### P&L per fill by venue, tier and reference price

![pnl](figures/pnl_by_tier.png)

*Figure 1. P&L per fill at the entry and top maker tiers, own-mid quoter (solid) and re-marked off the leading venue (hatched), with 95 % episode-bootstrap intervals. Base configuration: latency {{prm_latency_ms}} ms, {{base_qm}} queue model.*

{{table_headline}}

{{table_effect}}

### Where the fill's P&L goes

![attribution](figures/attribution.png)

*Figure 2. The four terms of the per-fill P&L at the top maker tier, own mid. Costs are drawn negative; the horizontal line is the net.*

{{table_attribution}}

![markouts](figures/markouts.png)

*Figure 3. Mark-out of the fills at 1, 10 and 60 s (positive = the fill made money against the later mid), own mid (filled markers) and re-marked (open).*

{{table_markouts}}

### Sensitivity: latency, queue model, half-spread multiplier

![sensitivity](figures/sensitivity.png)

*Figure 4. Top-tier P&L per fill against one-way latency, under each queue-position model (Bitstamp also with the order-id exact queue), and against the half-spread multiplier $c_\delta$ (fills per hour above the bars).*

{{table_sensitivity}}

### Lead-lag

![leadlag](figures/leadlag.png)

*Figure 5. The Hayashi–Yoshida contrast $\rho(\theta)$ per venue pair under the three clocks; the vertical line and label mark $\theta^*$ and the LLR on the exchange clock.*

{{table_leadlag}}

![session](figures/session.png)

*Figure 6. The three mids over the recording and the Coinbase and Bitstamp bases to Binance in bp.*

---

## Validation

- Queue models: trades consume the front and execute us past zero; arrivals never move us forward; a cancel is split by queue share (naive) or $x^3$ (power) and all behind us (risk-averse); recorded trades are not double-counted as cancels — worked examples of hftbacktest's rules.
- Books: Binance's snapshot rule on a constructed stream (drop, span, chain, gap); Coinbase absolute sizes and the maker-side convention; Bitstamp order aggregation with the snapshot replay, the order-id aggressor rule and an exactly-zero level after deletions; a torn gzip tail is read to the last complete line.
- Quoter: symmetric post-only quotes at flat inventory, downward skew when long, one side withdrawn at the bound, the half spread never tighter than the venue's or a tick, the EWMA volatility converging to the generating value.
- Replay and P&L: on a hand-made tape a sweep through the resting bid fills it at the right time, price and size, the episode flattens at the far touch, the mark-outs and the four attribution terms take their hand-computed values and sum to the realised P&L; latency delays the placement; the bootstrap recovers a known mean and a known paired difference.
- Lead-lag: the HY sum equals the realised covariance on synchronous data and the lagged cross-covariance for a whole-step shift; a known lag on Poisson-sampled Brownian motions is recovered and flips with the leg order; the block bootstrap covers the estimate.

## Limits, stated

- **One session on one day** ({{rec_date}}, {{session_hours}} h, a London afternoon into the US session). The intervals are over episodes within that session and say nothing about other days, regimes or hours; the numbers are the method's output on this tape, not a forecast.
- The replay has no impact and no reaction: our quotes are invisible to the recorded participants, and the queue position on Binance and Coinbase is a model (three variants, all reported). The `through` and `cross` rules are optimistic for a maker (a sweep that reaches our price fills us in full) and the owner's earlier Bitstamp check found the L2 models over-estimate the queue ahead by about 20 %; the Bitstamp `l3_exact` row is the honest comparison and it is on one venue only.
- Clocks: exchange timestamps are assumed to agree with each other, the latency is symmetric, and Binance's mid is only observed every 100 ms (Coinbase's every 50 ms), which blurs the lead-lag and the re-marking signal at exactly the scale where it would matter most.
- The quoter is deliberately simple (one lot, volatility-scaled half spread and skew, fixed pull horizon) and its parameters were set a priori; the $c_\delta$ row shows how fast the answer moves with the width. No parameter was tuned to the tape.
- Fees: two of the three venue pages could not be machine-read on the day; those tiers are third-party reproductions dated 2026 and must be re-read before any use beyond this exercise. The BNB discount, rebates and liquidity-programme terms are not applied.
- One lot of {{lot_btc}} BTC is small on these books; nothing here scales to size.

## Reproduce

```
pip install -e .[test]
python -m pytest
python -m cvq.recorder --out data/raw --binance-bbo BTCUSDT --minutes 320     # or any length; STOP file to end early
scripts/run_all.sh                                                             # books, lead-lag, replay, figures, summary, README
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

- **Cross-venue passive quoter on Binance, Coinbase and Bitstamp BTC books** | Python, websockets, parquet | `cross-venue-crypto-quoter` — Recorded {{session_hours}} h of three public order-book feeds (Bitstamp order by order), rebuilt the books, and replayed a one-lot inventory-skewed GLFT quoter with queue-position fills and latency: per fill the quoter {{binance_top_word_sig0}} on Binance at the VIP 9 maker tier, {{coinbase_top_word_sig0}} on Coinbase and {{bitstamp_top_word_sig0}} on Bitstamp at their top tiers, and loses {{binance_entry_pnl_sig0}} / {{coinbase_entry_pnl_sig0}} / {{bitstamp_entry_pnl_sig0}} bp at the entry tiers, with the fee and the 60 s adverse selection attributed exactly; Hayashi–Yoshida lead-lag between the venues' mids on three clocks, and the re-marked variant {{coinbase_effect_top_word}} on Coinbase and {{bitstamp_effect_top_word}} on Bitstamp.
