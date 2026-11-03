# cross-venue-crypto-quoter

A one-lot market-making quoter replayed on {{session_hours}} hours of BTC spot order books I recorded from Binance, Coinbase and Bitstamp on {{rec_date}}, in a Python package (`cvq`): a websocket recorder, book rebuilders, an inventory-skewed Avellaneda–Stoikov quoter, a replay with queue-position fills, an exact P&L attribution per fill and a cross-venue lead-lag study.

The question: what does a passive quoter earn per fill once spread capture, adverse selection, inventory and the maker fee are all charged, at the entry and the top fee tier, and does quoting off the venue that leads add anything?

## Results

- **The fee decides it.** At the entry maker tier every venue loses per fill: Binance {{binance_entry_pnl_sig0}} bp, Coinbase {{coinbase_entry_pnl_sig0}} bp and Bitstamp {{bitstamp_entry_pnl_sig0}} bp, because the fee is an order of magnitude larger than the half spread these books offer. At the top tier the losses shrink to {{binance_top_pnl_sig0}}, {{coinbase_top_pnl_sig0}} and {{bitstamp_top_pnl_sig0}} bp.
- **Fills are adversely selected.** The 60 s mark-out of a fill is {{binance_mo60_sig0}} bp on Binance, {{coinbase_mo60_sig0}} on Coinbase and {{bitstamp_mo60_sig0}} on Bitstamp, against spread capture of {{binance_top_spread_sig0}} / {{coinbase_top_spread_sig0}} / {{bitstamp_top_spread_sig0}} bp. {{binance_share_through_cross_sig0}} % of Binance fills ({{coinbase_share_through_cross_sig0}} % Coinbase, {{bitstamp_share_through_cross_sig0}} % Bitstamp) come from the price running through the quote, not from the queue draining.
- **Binance and Coinbase lead Bitstamp.** On the exchanges' own timestamps Binance leads Bitstamp by {{ll_binance_bitstamp_exchange_theta}} (lead-lag ratio {{ll_binance_bitstamp_exchange_llr}}) and Coinbase leads it by {{ll_coinbase_bitstamp_exchange_theta}} ({{ll_coinbase_bitstamp_exchange_llr}}). Binance and Coinbase cannot be separated at their feeds' 50–100 ms batching.
- **Quoting off the leader adds nothing measurable** at the top tier: {{coinbase_effect_top}} bp per fill on Coinbase, {{bitstamp_effect_top}} on Bitstamp and {{binance_effect_top}} on Binance, paired by episode.

P&L per fill in bp for the own-mid quoter ({{prm_latency_ms}} ms latency, `{{base_qm}}` queue model), with 95 % intervals from resampling the {{n_episodes}} {{episode_min}}-minute episodes:

| venue | fills | maker fee, entry → top tier (bp) | entry tier | top tier | 60 s mark-out |
|---|---|---|---|---|---|
| Binance BTCUSDT | {{binance_fills_sig0}} | {{binance_entry_bp}} → {{binance_top_bp}} | {{binance_entry_pnl_sig0}} | {{binance_top_pnl_sig0}} | {{binance_mo60_sig0}} |
| Coinbase BTC-USD | {{coinbase_fills_sig0}} | {{coinbase_entry_bp}} → {{coinbase_top_bp}} | {{coinbase_entry_pnl_sig0}} | {{coinbase_top_pnl_sig0}} | {{coinbase_mo60_sig0}} |
| Bitstamp BTC/USD | {{bitstamp_fills_sig0}} | {{bitstamp_entry_bp}} → {{bitstamp_top_bp}} | {{bitstamp_entry_pnl_sig0}} | {{bitstamp_top_pnl_sig0}} | {{bitstamp_mo60_sig0}} |

![P&L per fill by venue and fee tier](figures/pnl_by_tier.png)
![Where each fill's P&L goes](figures/attribution.png)

All numbers are in `results/summary.md`; the method, the data and every table are in [docs/method.md](docs/method.md).

## How it works

- **Recording.** The venues' public websockets ({{raw_mb_total}} MB gzip, {{raw_lines_total}} messages, no key): Binance depth and trades, Coinbase level 2 and matches, and Bitstamp's order-by-order feed. Each book is rebuilt to the exchange's own sequencing rules and reset every hour.
- **Quoter.** Avellaneda–Stoikov in the stationary GLFT form, in bp of the mid: the half spread and the inventory skew scale with the mid's EWMA volatility, {{lot_btc}} BTC per order, quotes pulled after {{prm_T}} s, inventory capped at {{prm_max_inventory}} lots.
- **Replay.** Exchange event time with {{prm_latency_ms}} ms latency each way. A resting quote fills when the queue ahead of it is consumed (three L2 queue models, checked against Bitstamp's order ids), when a trade runs through it, or when the book crosses it. Inventory is flattened every {{episode_min}} minutes.
- **P&L.** Each fill splits exactly into spread capture, adverse selection (the 60 s mark-out), inventory and the maker fee, at each venue's published fee tiers.
- **Lead-lag.** Hayashi–Yoshida cross-correlation with the Huth–Abergel lead-lag ratio, on the exchanges' clocks and on the recorder's.

## Limitations

- One session of {{session_hours}} hours on one day, so the intervals are over episodes within it.
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

The README and `docs/method.md` are generated from `scripts/*.template.md` by `scripts/readme.py`, so every number is the run's; CI runs the {{n_tests}} tests and re-renders both from the committed results.
