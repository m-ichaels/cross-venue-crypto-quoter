# Data sources

Everything in this repository was recorded by `cvq/recorder.py` from the venues' public, keyless websocket and REST
endpoints in one session on 2026-10-07, from a laptop in London. No data was bought and nothing is simulated except
the known-answer tests. Sizes, message counts, gaps and resyncs per hour are in `results/books.json` and in the
"Recording" table of `results/summary.md`.

| venue | instrument | streams | timestamps | notes |
|---|---|---|---|---|
| Binance spot | BTCUSDT | `wss://stream.binance.com:9443/stream?streams=btcusdt@depth@100ms/btcusdt@trade`; REST `GET /api/v3/depth?symbol=BTCUSDT&limit=5000` once per (re)synchronisation | `E` event time (ms) on depth, `T` trade time (ms) on trades; `rx` = local receive time (ns) on every line | depth diffs every 100 ms (the mid is observed at 100 ms resolution); book synchronised with the documented `U/u` rule; one snapshot is weight 250, fetched only on a gap |
| Binance spot | BTCUSDT | `btcusdt@bookTicker` (venue folder `binance_bbo`) | none from the exchange; `rx` only | real-time best bid/ask on every change, recorded for the sub-100 ms lead-lag check |
| Coinbase Exchange | BTC-USD | `wss://ws-feed.exchange.coinbase.com`, channels `level2_batch` (snapshot + absolute-size updates batched every 50 ms), `matches`, `heartbeat` | ISO-8601 `time` (µs) | the unbatched `level2` and the order-by-order `full` channel require an API key since 2023; `match.side` is the maker's side |
| Bitstamp | BTC/USD (`btcusd`) | `wss://ws.bitstamp.net`, channels `live_orders_btcusd` (order created / changed / deleted with order ids), `live_trades_btcusd` (with buy and sell order ids); REST `GET /api/v2/order_book/btcusd/?group=2` once the stream is live (rows carry order ids) | `microtimestamp` (µs) | the only free order-by-order (L3) feed of the three; the L2 book is the per-price aggregate of the order map |

## Raw files

`data/raw/<venue>/<YYYY-MM-DD>/<HH>.jsonl.gz` (gitignored: 200-300 MB per 5 hours), one JSON object per line,
written before any parsing, in receive order:

```
{"rx": <ns since the epoch, local clock>, "venue": "binance"|"binance_bbo"|"coinbase"|"bitstamp",
 "kind": "ws"|"snapshot"|"meta", "msg": <the payload verbatim>}
```

`kind = meta` lines are the recorder's own events (connect, disconnect, gap, resync, shutdown). A copy of the raw
files with this description sits outside the repository in `C:\Users\maver\builds\_data\crypto_books\` for reuse.

Regenerate a recording (any length; the analysis scripts take whatever hours exist):

```
python -m cvq.recorder --out data/raw --binance-bbo BTCUSDT --minutes 320
```

## Derived tables

`data/derived/<venue>/<YYYY-MM-DDTHH>_{msgs,l2,trades,bbo,l3}.parquet` (gitignored, rebuilt by
`python scripts/build_books.py` in a few minutes): per-hour normalised tables documented in `cvq/books.py`. Each hour
file begins with a full-book reset so it can be read alone. `data/fills/` (committed) holds one fills table and one
episodes table per replay configuration, with the mark-outs and the per-tier attribution columns, which is what the
summary, the figures and the README are built from.

## Clocks

Receive-minus-exchange time (network delay plus the laptop's clock offset) had a median of about 260 ms for Binance,
200 ms for Coinbase and 180-250 ms for Bitstamp during the recording (`recorder.log`). The analysis uses each
venue's exchange timestamps as the event clock and reports the receive-clock lead-lag as a variant; neither clock
offset is corrected.

## Fee schedules

`configs/fees.json` and `data/fees/README.md` (sources and dates; two of the three venue pages could not be read by
script on 2026-10-07 and the figures come from the stated secondary sources).
