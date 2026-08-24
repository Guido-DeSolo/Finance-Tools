# DF-FinTechTerm capability dossier

Snapshot date: 2026-08-24

Repository: `Finance-Tools`

Application root: `current/DF-FinTechTerm`

This document is intended to be portable context for an external technical
review. It describes implemented behavior, operational boundaries, storage,
safety controls, known limitations, and the distinction between background
services and user actions. Planned work is labeled explicitly.

## Executive summary

DF-FinTechTerm is a local terminal-based finance and trading research system.
It combines:

- an interactive Alpaca account, market-data, and order-management TUI;
- an embedded Finance Shell with calculators, data collection, classification,
  sentiment, technical analysis, and service controls;
- scheduled PostgreSQL research ingestion and deterministic scoring services;
- narrow Ollama specialist adapters and frozen evaluation benchmarks;
- a live Alpaca WebSocket daemon backed by SQLite;
- reusable Python packages for Alpaca account operations, Alpaca market data,
  and dependency-free technical indicators.

The application distinguishes operations by behavior:

- **Services** are supervised, scheduled, or continuously running background
  workers that collect or derive data.
- **Actions** are finite operations initiated by a user, including queries,
  research generation, benchmarks, calculations, and trading commands.

The default research execution mode is `backtest`. Alpaca account clients and
the TUI default to paper trading. No autonomous strategy-to-order pipeline is
implemented.

## Top-level invocation

From `current/DF-FinTechTerm`:

```bash
./run.sh                         # start the terminal UI
./run.sh fsh help                # Finance Shell command catalog
./run.sh services                # list scheduled/background services
./run.sh service NAME [ARGS]     # run one service in the foreground
./run.sh actions                 # list finite research actions
./run.sh action NAME [ARGS]      # run one research action
./run.sh catalog                 # emit service/action catalog as JSON
```

## Background services

### Live market stream daemon

The continuously running Alpaca stream daemon is controlled through:

```bash
./run.sh fsh alpaca stream start
./run.sh fsh alpaca stream stop
./run.sh fsh alpaca stream restart
./run.sh fsh alpaca stream status
```

Implemented behavior:

- maintains one persisted watchlist for stock and crypto symbols;
- groups WebSocket connections by asset class, feed, and crypto location;
- supports IEX or SIP stock feeds and Alpaca crypto locations;
- subscribes to trades and stock quotes or crypto order books;
- subscribes separately to relevant Alpaca news;
- reconnects with bounded exponential backoff;
- appends deduplicated raw market events;
- stores normalized trades and current order-book state in SQLite;
- preserves full crypto depth and stock top-of-book quotes;
- updates article-to-symbol relationships;
- warms rolling buffers from stored trades;
- updates one-minute OHLCV buffers after every trade;
- recalculates OBV, ADX, ADL, Aroon, MACD, RSI, and stochastic values after
  each trade; and
- stores the latest technical-analysis snapshot per watched market identity.

The controller installs a user-level systemd service, writes credentials only
to `~/.config/finance-shell/alpaca.env` with mode `0600`, and restarts the daemon
when an active watchlist changes.

### Scheduled PostgreSQL services

These services are registered in the machine-readable application catalog:

| Service | Side effect | Implemented function |
|---|---|---|
| `market-minute` | PostgreSQL writes | Paginated Alpaca IEX one-minute bar ingestion; currently configured for SPY from 2024 onward |
| `market-daily-iex` | PostgreSQL writes | Batched adjusted daily IEX bars for the insider-derived symbol universe |
| `market-daily-sip` | PostgreSQL writes | Batched adjusted daily SIP bars for the same universe |
| `news-ingest` | PostgreSQL writes | Paginated Alpaca news article ingestion and upsert |
| `insider-ingest` | PostgreSQL writes | OpenInsider-style Form 4 collection, parsing, normalization, and persistence |
| `watchlist-refresh` | PostgreSQL writes | Deterministic insider/news/market candidate scoring |

Each service can run in the foreground through `./run.sh service NAME`. A
generic `backend/systemd/df-fintechterm@.service` template permits each named
worker to be supervised independently. These ingestion programs are currently
batch jobs rather than permanent event loops.

## Registered research actions

| Action | Persistence | Implemented function |
|---|---|---|
| `candidate-packets` | JSON artifact | Builds and validates ranked evidence packets from PostgreSQL |
| `insider-backtest` | None | Exploratory forward-return study of insider purchase events |
| `analyst` | PostgreSQL | Sends reduced evidence to an Ollama analyst, validates its structured response, and stores complete provenance |
| `benchmark-analyst` | Result artifact | Runs frozen general analyst benchmark v1 |
| `benchmark-news-v1` | Result artifact | Runs the preserved broad NEWS v1 benchmark |
| `benchmark-news-v2` | Result artifact | Runs narrow per-article NEWS v2 benchmark |
| `benchmark-quant-v1` | Result artifact | Runs preserved model-based QUANT benchmark |
| `benchmark-quant-v2` | Result artifact | Runs deterministic QUANT regression benchmark |
| `benchmark-synthesis` | Result artifact | Runs normalized-signal synthesis benchmark |

Frozen manifests hash the relevant source, corpora, and benchmark code so model
or contract changes cannot silently redefine a previously accepted baseline.

## Terminal UI capabilities

The curses TUI provides:

- paper/live mode banner and connection status;
- account equity, cash, buying power, and current-day P&L;
- positions with quantity, market value, average entry, current price, and
  unrealized P&L;
- recent orders and their current status;
- stock snapshots and a scrolling BTC/USD quote/order-book ticker;
- a NewsData.io pane;
- a local Ollama chat pane with a single hard-coded model constant;
- a full-screen live technical-analysis viewport;
- most-recently-updated-first watched-symbol ordering;
- indicator buffer depth and update age;
- display of RSI, ADX, MACD, signal, histogram, OBV, ADL, Aroon up/down, and
  stochastic K/D;
- watched-symbol editing;
- buy and sell order entry;
- market, limit, stop, and stop-limit orders;
- quantity or dollar-notional sizing;
- open-order cancellation;
- complete-position closing; and
- access to the entire Finance Shell catalog without leaving the application.

The TUI requires an 80x20 terminal. It polls REST account/snapshot data while
the separate stream daemon handles live collection.

## Finance Shell user actions

### Market and research data

- `indicators test`: run the legacy deterministic indicator suite.
- `indicators report`: render its validation report.
- `indicators example`: show deterministic example data.
- `price bitcoin`: fetch current BTC/USD price.
- `price silver`: fetch current silver price using `METALPRICE_API_KEY`.
- `tickrs`: launch Tickrs against symbols with stored data.
- `ticker`: launch Ticker against symbols with stored data.
- `tickrs-industry`: select an industry and launch its stored symbols.
- `classify refresh`: classify stored stocks with SEC SIC metadata.
- `classify list`: view stored classifications.
- `sentiment analyze ARTICLE_ID`: classify a stored article with local Ollama.
- `sentiment pending`: classify articles lacking a result.
- `sentiment list [SYMBOL]`: view stored sentiment results.

### Alpaca data operations

- `alpaca sync-assets`: persist stock and crypto asset catalogs.
- `alpaca history`: download paginated historical stock or crypto bars.
- `alpaca history-list FILE`: ingest full one-minute history for symbols not
  already represented in the target database.
- `alpaca status`: report local database counts.
- `alpaca news [SYMBOL]`: show newest stored real-time news.
- `alpaca analysis [SYMBOL]`: show latest per-trade indicator snapshots.
- `alpaca timeframes`: list supported historical timeframe/window rules.

### Live stream operations

- `alpaca stream add SYMBOL --class stock|crypto`: add a persisted watch.
- `alpaca stream remove SYMBOL --class stock|crypto`: remove it.
- `alpaca stream list`: inspect the persisted stream watchlist.
- `alpaca stream start|stop|restart|status`: supervise the live daemon.
- `alpaca stream view [SYMBOL]`: render live books and trades.

### Deterministic calculators

- compound growth with optional periodic contribution;
- gain/loss amount and percentage;
- remaining budget and savings rate; and
- weighted or percentage allocation of a total.

### System operation

`doctor` verifies Python, source syntax, WebSocket support, the local SQLite
schema, indicator tests, optional Ollama availability, and optional metals-key
configuration without performing trading operations.

## Reusable Python packages

### Alpaca account and trading API

`packages/alpaca-account-api` is a dependency-free wrapper with a
machine-readable manifest covering 57 Alpaca Trading API operations:

- complete account records and account configuration;
- account activities and portfolio history;
- assets, clocks, calendars, announcements, and option contracts;
- submit/list/get/replace/cancel orders;
- lookup by client order ID;
- list/get/close positions;
- cancel-before-liquidation;
- option exercise and do-not-exercise;
- locates and locate quotes;
- tokenization minting and request tracking;
- crypto wallets, fee estimates, transfers, and address whitelists;
- watchlists by UUID and name; and
- server-sent account and trade activity events.

Responses remain unmodified JSON so uncommon account fields are retained. A raw
request escape hatch and response-metadata API expose request IDs, headers, and
rate-limit information. Paper mode is the default, although mutating wrapper
methods execute immediately when called and do not add confirmation prompts.

### Alpaca market-data package

`packages/alpaca-data` provides:

- assets, snapshots, latest quotes/trades, and crypto order books;
- paginated historical stock and crypto bars;
- Alpaca news retrieval;
- stock, crypto, and news WebSocket collection;
- reconnect handling;
- SQLite schemas and idempotent persistence;
- append-only deduplicated raw market events;
- stored stream views and watchlist helpers;
- SEC industry classification; and
- local Ollama sentiment for stored articles.

The core uses only the standard library; live streams optionally require
`websockets`.

### Technical-indicator package

`packages/technical-indicators` contains dependency-free, typed implementations
of OBV, ADX, ADL, Aroon, MACD, RSI, and stochastic oscillators with aligned
series, validation, lowercase names, and conventional uppercase aliases.

## Deterministic research and model boundaries

Implemented deterministic stages include:

- candidate scoring from insider, news-count, and market evidence;
- candidate packet construction and structural validation;
- OHLC quality checks and finite-number validation;
- daily returns, volatility, volume ratios, and rolling-high/low distance;
- categorical trend, momentum, volatility, and volume signals;
- deterministic signal-strength normalization and risk flags;
- news lookback filtering, future-boundary exclusion, deduplication, stable IDs,
  and explicit no-news abstention;
- deterministic NEWS v2 aggregation, conflict detection, counts, balance,
  confidence, and materiality summaries; and
- deterministic insider activity reduction.

NEWS v2 restricts the model to classifying each supplied article's sentiment
and materiality. Python owns aggregation and no-news behavior. Older NEWS v1
and model QUANT versions remain as frozen research artifacts rather than being
silently discarded.

The synthesis model receives only whitelisted normalized branch signals. Its
output is research interpretation, not an executable portfolio decision.

## Storage

Two existing storage paths serve different workloads:

- SQLite stores local asset catalogs, bars, fetch runs, live trades, current
  quotes/order books, raw stream events, live news, sentiment, classifications,
  the stream watchlist, and rolling analysis snapshots.
- PostgreSQL stores minute/daily bars, Alpaca news, normalized insider trades,
  insider feature views, watchlist scores, and structured analyst results.

Database files, WAL/SHM sidecars, `.env` files, credentials, caches, and generated
candidate packets are excluded from Git.

## Safety properties

- Repository name remains `Finance-Tools`.
- TUI and account wrapper default to Alpaca paper trading.
- `DF_FINTECHTERM_MODE` defaults to `backtest` and validates
  `backtest|shadow|paper|live`.
- The shared runtime contract requires a second exact `LIVE` acknowledgement for
  future live execution entry points.
- Current research services do not place orders.
- The TUI displays live mode prominently and requires both `YES` and `LIVE`
  confirmations before a real-money order or position close.
- Models receive constrained prepared inputs rather than unrestricted database or
  broker access.
- Credentials are supplied through environment/config files and are not tracked.
- The metals-price source contains no embedded API key.

## Implemented tests

Current validated baseline:

- 62 backend/research tests;
- 12 terminal/helper tests;
- 20 Finance Shell/live-data tests;
- 94 tests total.

Coverage includes frozen artifact hashes, model-response schemas, evidence
references, abstention, packet validation, market quality, deterministic signal
contracts, news aggregation, raw-event deduplication, live order books, stream
startup, historical pagination, sentiment validation, and terminal catalogs.

## Known limitations and not-yet-implemented architecture

The following should not be represented as existing capability:

- no autonomous signal-to-order trading loop;
- no canonical typed BUY/SELL/HOLD/CASH decision ledger;
- no deterministic portfolio-sizing engine;
- no pluggable fee model yet;
- no pluggable slippage/fill simulator yet;
- no independent proposal-reducing/rejecting risk engine;
- no general historical replay engine with enforced information cutoffs;
- no decision outcome evaluator across 5m/15m/1h/4h/1d horizons;
- no counterfactual decision scoring;
- no unified USD/asset portfolio accounting ledger;
- no cash, buy-and-hold, DCA, SMA, or random portfolio baselines;
- no normalized order-book microstructure feature package;
- no deterministic 1m-to-multiple-horizon aggregation engine;
- PostgreSQL contents and the claimed large historical universe have not been
  inventoried from this host because the mounted source's private environment was
  unreadable; and
- stock live books are top-of-book only, while crypto supports full depth.

## Suggested external-review questions

1. Are service/action classifications accurate and sufficiently enforceable?
2. Which duplicated SQLite and PostgreSQL market-data responsibilities should be
   unified first without migrating working databases destructively?
3. Is `DF_FINTECHTERM_MODE` strong enough, or should live execution require a
   separate executable or compile-time-disabled adapter?
4. What canonical immutable contracts should precede fees, slippage, decisions,
   orders, fills, and evaluations?
5. Which existing deterministic features are mathematically sound and which need
   benchmark fixtures against an independent reference implementation?
6. How should the stream daemon and batch services expose health, lag, last
   successful checkpoint, and failure state to the terminal?
7. What is the smallest replay/evaluation slice that proves look-ahead prevention
   and net-of-cost accounting before additional model integration?
