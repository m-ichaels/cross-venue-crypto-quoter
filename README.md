# cross-venue-crypto-quoter

A one-lot market-making quoter replayed on 5.0 hours of BTC spot order books I recorded from Binance, Coinbase and Bitstamp on 2026-10-07, in a Python package (`cvq`): a websocket recorder, book rebuilders, an inventory-skewed Avellaneda–Stoikov quoter, a replay with queue-position fills, an exact P&L attribution per fill and a cross-venue lead-lag study.

The question: what does a passive quoter earn per fill once spread capture, adverse selection, inventory and the maker fee are all charged, at the entry and the top fee tier, and does quoting off the venue that leads add anything?

## Results

- **The fee decides it.** At the entry maker tier every venue loses per fill: Binance -11.57 [-11.74, -11.42] bp, Coinbase -40.86 [-41.04, -40.68] bp and Bitstamp -32.36 [-33.20, -31.78] bp, because the fee is an order of magnitude larger than the half spread these books offer. At the top tier the losses shrink to -2.51 [-2.66, -2.38], -0.49 [-0.57, -0.40] and -1.15 [-1.31, -1.02] bp.
- **Fills are adversely selected.** The 60 s mark-out of a fill is -1.33 [-1.56, -1.13] bp on Binance, -0.47 [-0.56, -0.38] on Coinbase and -1.03 [-1.22, -0.87] on Bitstamp, against spread capture of 0.32 [0.28, 0.35] / 0.42 [0.37, 0.48] / 0.03 [-0.01, 0.07] bp. 49 % of Binance fills (93 % Coinbase, 86 % Bitstamp) come from the price running through the quote, not from the queue draining.
- **Binance and Coinbase lead Bitstamp.** On the exchanges' own timestamps Binance leads Bitstamp by 180 ms [140, 320] (lead-lag ratio 1.75 [1.48, 2.14]) and Coinbase leads it by 120 ms [120, 300] (2.01 [1.66, 2.40]). Binance and Coinbase cannot be separated at their feeds' 50–100 ms batching.
- **Quoting off the leader adds nothing measurable** at the top tier: +0.05 [-0.02, +0.12] bp per fill on Coinbase, +0.14 [-1.08, +1.02] on Bitstamp and -0.14 [-0.47, +0.15] on Binance, paired by episode.

P&L per fill in bp for the own-mid quoter (50 ms latency, `naive_fifo` queue model), with 95 % intervals from resampling the 20 15-minute episodes:

| venue | fills | maker fee, entry → top tier (bp) | entry tier | top tier | 60 s mark-out |
|---|---|---|---|---|---|
| Binance BTCUSDT | 2277 | 10 → 1.1 | -11.57 [-11.74, -11.42] | -2.51 [-2.66, -2.38] | -1.33 [-1.56, -1.13] |
| Coinbase BTC-USD | 2467 | 40 → 0 | -40.86 [-41.04, -40.68] | -0.49 [-0.57, -0.40] | -0.47 [-0.56, -0.38] |
| Bitstamp BTC/USD | 1223 | 30 → 0 | -32.36 [-33.20, -31.78] | -1.15 [-1.31, -1.02] | -1.03 [-1.22, -0.87] |

![P&L per fill by venue and fee tier](figures/pnl_by_tier.png)
![Where each fill's P&L goes](figures/attribution.png)

All numbers are in `results/summary.md`; the method, the data and every table are in [docs/method.md](docs/method.md).

## How it works

- **Recording.** The venues' public websockets (175 MB gzip, 5,842,169 messages, no key): Binance depth and trades, Coinbase level 2 and matches, and Bitstamp's order-by-order feed. Each book is rebuilt to the exchange's own sequencing rules and reset every hour.
- **Quoter.** Avellaneda–Stoikov in the stationary GLFT form, in bp of the mid: the half spread and the inventory skew scale with the mid's EWMA volatility, 0.01 BTC per order, quotes pulled after 10 s, inventory capped at 5 lots.
- **Replay.** Exchange event time with 50 ms latency each way. A resting quote fills when the queue ahead of it is consumed (three L2 queue models, checked against Bitstamp's order ids), when a trade runs through it, or when the book crosses it. Inventory is flattened every 15 minutes.
- **P&L.** Each fill splits exactly into spread capture, adverse selection (the 60 s mark-out), inventory and the maker fee, at each venue's published fee tiers.
- **Lead-lag.** Hayashi–Yoshida cross-correlation with the Huth–Abergel lead-lag ratio, on the exchanges' clocks and on the recorder's.

## Limitations

- One session of 5.0 hours on one day, so the intervals are over episodes within it.
- Replay has no market impact: the quotes are not in the recorded book, and nobody reacts to them.
- Binance's and Bitstamp's fee tiers come from third-party reproductions, because their own pages could not be read by script.
- One coin, three venues, one lot.

## Run

```
pip install -e .[test]
python -m pytest
python -m cvq.recorder --out data/raw --binance-bbo BTCUSDT --minutes 320   # record a session
scripts/run_all.sh                                                           # books, lead-lag, replay, figures, summary, README
```

The README and `docs/method.md` are generated from `scripts/*.template.md` by `scripts/readme.py`, so every number is the run's; CI runs the 25 tests and re-renders both from the committed results.
