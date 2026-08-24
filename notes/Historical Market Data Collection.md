---
tags:
  - finance
  - market-data
  - sqlite
  - alpaca
---

# Historical Market Data Collection

The historical collector is the long-term market-data layer of the
[[Finance Suite]]. It requests timestamped price bars from Alpaca, follows the
API's pagination, and stores normalized OHLCV records in the shared finance
SQLite database.

Unlike the live daemon, it is run as a bounded command: request a symbol,
timeframe, and date range; collect every available page; write the bars; record
the result; then exit.

## Role in the finance system

```text
Alpaca historical bars API
            ↓
`fsh alpaca history`
            ↓
pagination + validation + normalization
            ↓
SQLite `bars` + `fetch_runs`
            ↓
symbol discovery / Tickrs / Ticker / classification / analysis
```

Historical bars provide context that a newly started live stream cannot. They
allow the database to contain an established price series immediately instead
of waiting minutes, days, or months for live events to accumulate.

Within the larger suite, the stored data:

- Establishes which symbols have actual market data rather than merely
  appearing in Alpaca's asset catalog.
- Supplies unique symbols to the database-driven `tickrs` and `ticker`
  launchers.
- Gives industry-classification tooling a set of populated symbols to process.
- Provides OHLCV series suitable for later indicators, comparisons, reports,
  charting, research, and model features.
- Complements live trades, quotes, and order books without mixing their raw
  event semantics into candle/bar records.
- Creates an auditable record of collection attempts through `fetch_runs`.

Historical data is not a replacement for live data. The two layers answer
different questions:

| Layer | Primary purpose |
| --- | --- |
| Historical `bars` | Price and volume over defined time windows and date ranges |
| Live events/trades/books | Current trades, quotes, order-book changes, and reconstructed state |
| News and sentiment | Event context and local model interpretation |
| Symbol classifications | Industry and sector metadata |

## Commands

Daily stock bars from a chosen date:

```bash
fsh alpaca history AAPL --class stock --timeframe 1Day --start 2020-01-01
```

All available one-minute IEX stock history:

```bash
fsh alpaca history AAPL \
    --class stock \
    --timeframe 1Min \
    --start 1970-01-01 \
    --feed iex
```

Crypto history:

```bash
fsh alpaca history BTC/USD \
    --class crypto \
    --timeframe 1Hour \
    --start 2024-01-01 \
    --location us
```

Useful controls include:

- `--timeframe` for the requested aggregation window.
- `--start` and `--end` for the requested date range.
- `--feed` for the stock data source, with IEX as the default.
- `--adjustment` for the requested stock adjustment policy.
- `--location` for the crypto data location.
- `--max-pages` for a deliberately small test or partial collection.
- `fsh alpaca timeframes` to show accepted timeframe formats.

The smallest quick test is typically:

```bash
fsh alpaca history AAPL --class stock --timeframe 1Min --start 1970-01-01 --feed iex --max-pages 1
```

That run is intentionally recorded as `partial` when another page was
available.

## Batch collection

For one stock symbol per line:

```text
AAPL
MSFT
NVDA
# Blank lines and comments are ignored
```

Run:

```bash
fsh alpaca history-list symbols.txt
```

The batch script:

- Trims whitespace and normalizes symbols to uppercase.
- Ignores blank lines and lines beginning with `#`.
- Requests one-minute IEX history from `1970-01-01` so Alpaca can return its
  earliest available data.
- Continues to later symbols if one request fails.
- Reports a failing exit status if any symbol failed.
- Skips a symbol when **any** stock bars for it already exist.

That final rule prevents unnecessary large downloads, but it is deliberately
coarse. A symbol with only a partial test page is still skipped. Use the
single-symbol command to finish or repeat it. A future improvement could track
coverage by timeframe, feed, adjustment, start, end, and completed fetch run
instead of treating any row as complete coverage.

## The `bars` table

Each bar records:

| Field | Meaning |
| --- | --- |
| `asset_class` | `stock` or `crypto` |
| `symbol` | Normalized symbol such as `AAPL` or `BTC/USD` |
| `timeframe` | Requested aggregation window such as `1Min` or `1Day` |
| `timestamp` | Alpaca bar timestamp |
| `open`, `high`, `low`, `close` | OHLC prices |
| `volume` | Bar volume |
| `trade_count` | Number of trades when supplied |
| `vwap` | Volume-weighted average price when supplied |
| `feed` | Stock feed or crypto location |
| `adjustment` | Stock adjustment policy |
| `fetched_at` | When this copy was stored |

The composite primary key is:

```text
asset_class + symbol + timeframe + timestamp + feed + adjustment
```

Repeated collection is therefore idempotent at the bar identity level. A
matching row is updated rather than duplicated, including its OHLCV values and
`fetched_at` timestamp. Different timeframes, feeds, locations, or adjustment
policies can coexist.

An index on asset class, symbol, timeframe, and timestamp supports chronological
series lookups.

## The `fetch_runs` table

Every historical command creates a run record before downloading. It records:

- Asset class, symbol, and timeframe.
- Requested start and end.
- Start and finish timestamps.
- Pages processed and rows saved.
- Final status.
- A bounded error message on failure.

Run statuses are:

| Status | Meaning |
| --- | --- |
| `running` | Collection began but has not finalized |
| `complete` | Pagination ended normally |
| `partial` | Collection stopped at `--max-pages` while more data was available |
| `failed` | API, validation, pagination, interruption, or storage error |

This table distinguishes “bars exist” from “the requested collection completed
successfully,” even though the current batch skip rule uses only bar existence.

## Pagination and failure safety

- Alpaca pages are requested in ascending time order.
- Each page is validated before its bars are saved.
- Progress is committed after each page, including current page and row counts.
- A repeated page token is treated as an error rather than looping forever.
- Invalid response shapes or tokens fail the run.
- An interrupted or failed run keeps successfully committed earlier pages and
  records the final error.
- Re-running the same request updates matching bars safely.

This means a failure can produce useful partial data, but downstream work that
requires complete coverage should consult `fetch_runs` rather than assuming
row presence proves completeness.

## Database relationship

The shared database is:

```text
/home/guyyatsu/Documents/finance-shell/data/alpaca.sqlite3
```

SQLite WAL mode allows the historical command and read-oriented tools to use
the database without folding every finance feature into one process. The
`-wal` and `-shm` files are part of active database state and must be considered
during backups.

Historical collection writes `bars` and `fetch_runs`. It does not modify the
live stream watchlist or start/stop the daemon. Likewise, adding a live symbol
does not automatically download historical bars. The operator chooses when to
populate each layer.

## Inspection

Collection status:

```bash
fsh alpaca status
```

Bar coverage by symbol and timeframe:

```bash
sqlite3 ~/Documents/finance-shell/data/alpaca.sqlite3 '
SELECT asset_class, symbol, timeframe, feed, adjustment,
       count(*) AS bars, min(timestamp), max(timestamp)
FROM bars
GROUP BY asset_class, symbol, timeframe, feed, adjustment
ORDER BY asset_class, symbol, timeframe;'
```

Recent fetch runs:

```bash
sqlite3 ~/Documents/finance-shell/data/alpaca.sqlite3 '
SELECT id, symbol, timeframe, requested_start, requested_end,
       pages, rows_saved, status, error
FROM fetch_runs
ORDER BY id DESC
LIMIT 20;'
```

## Operational considerations

- Load Alpaca credentials from the persistent environment file; never put them
  in SQLite, this vault, or source control.
- Confirm the requested feed is available to the Alpaca account.
- Expect one-minute maximum-history downloads to take time and consume
  substantial storage.
- Use `--max-pages 1` before a large new collection strategy.
- Check failed and partial `fetch_runs` after interruptions.
- Measure database and WAL growth before starting a large symbol list.
- Back up the database using a SQLite-aware method while writers may be active.
- Treat OHLCV data as research input, not as an assurance of completeness,
  accuracy, corporate-action treatment, or trading suitability.

## Current limitations and likely improvements

- Batch skipping is based on any existing stock bar, not complete coverage.
- Historical downloads are operator-triggered rather than scheduled.
- There is no automatic gap detector or repair pass.
- No retention or aggregation policy currently reduces old high-resolution
  bars.
- Completeness depends on Alpaca availability, entitlement, feed, and returned
  history.
- Downstream indicator/report pipelines should explicitly select asset class,
  timeframe, feed, adjustment, and date range.

## Related notes

- [[Finance Suite]]

