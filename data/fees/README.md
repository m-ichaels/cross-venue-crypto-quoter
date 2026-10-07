# Maker-fee schedules used (read 2026-10-07)

`configs/fees.json` carries the numbers the attribution uses; this file records where each one came from and what
could not be read. All fees are per trade, as a share of notional, in the venue's quote currency.

| venue | tier | threshold (30-day volume) | maker | taker | source |
|---|---|---|---|---|---|
| Binance spot | Regular user / VIP 0 | any | 0.10 % (10 bp) | 0.10 % | Binance support article 115000429332, fetched through the public CMS endpoint `binance.com/bapi/composite/v1/public/cms/article/detail/query?articleCode=115000429332` on 2026-10-07: "Each trade carries a standard fee of 0.1% for regular users." Saved as `binance_support_article_115000429332_2026-10-07.json`. |
| Binance spot | VIP 9 | >= $4 bn | 0.011 % (1.1 bp) | 0.023 % | `binance.com/en/fee/trading` is rendered by JavaScript behind a bot check (HTTP 202 shell on 2026-10-07) and could not be read by script. Figures from comparedge.com/tools/binance/pricing ("Verified July 8, 2026") and spotedcrypto.com's 2026-05-30 comparison, both reproducing the Binance VIP table (VIP 0 0.10 / 0.10 ... VIP 9 0.011 / 0.023). |
| Coinbase Exchange | $0K-$10K | < $10k | 40 bp | 60 bp | help.coinbase.com/en/exchange/trading-and-funding/exchange-fees, read 2026-10-07 (text extract saved as `coinbase_exchange_fees_help_page_2026-10-07.txt`). |
| Coinbase Exchange | $400M+ | >= $400 m | 0 bp | 4 bp | same page: maker 0 bp from the $250M-$400M tier up; taker 6 bp then 4 bp. |
| Bitstamp | < $10K | < $10k (first $1,000 fee-free) | 0.30 % (30 bp) | 0.40 % | `bitstamp.net/fee-schedule/` sits behind an Incapsula bot wall (212-byte challenge page on 2026-10-07) and could not be read by script. Figures from cryptoslate.com's Bitstamp review (updated 2026-10-06: "Maker 0.3% and Taker 0.4%" at entry, "0.00% maker and 0.03% taker" at the top), coinlaw.io (2026-05-14) and gncrypto.news (2026-05-06). The $1,000 allowance is Bitstamp's own: blog.bitstamp.net/post/lower-trading-fees-for-maker-orders-and-stablecoins/ (2022-12-15). |
| Bitstamp | $1B+ | >= $1 bn | 0.00 % (0 bp) | 0.03 % | as above. |

Notes.
- Coinbase: the recorded book is `ws-feed.exchange.coinbase.com` BTC-USD, i.e. Coinbase Exchange, whose schedule is
  public. The retail Coinbase Advanced schedule is shown only to signed-in users as of 2026-10-07 (the help page says
  so); third-party pages (coinlaw.io, 2026-05-14) give Intro 1 (< $1k) 60 bp maker and 0 bp maker from $250 m. Both
  books are the same matching engine; the Exchange schedule is used.
- Binance: paying fees in BNB takes 25 % off (VIP 0 maker 7.5 bp). Not applied. No BTC/USDT zero-fee promotion was
  in force according to the sources read.
- The taker fee of the same tier is charged on the end-of-episode flattening trade.
- Third-party reproductions are secondary sources; the venue pages are the authority and should be re-read before
  any use of these numbers beyond this exercise.
