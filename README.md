# Finance-Tools

Finance-Tools contains **DF-FinTechTerm**, a local terminal for Alpaca market
data, account operations, research, and paper/live order entry. It combines one
interactive TUI with discrete background services and reusable Python packages.

Paper trading is the default. No service autonomously places orders, and live
orders require an additional explicit confirmation.

## Project layout

```text
DF-FinTechTerm/
  df_fintech_term/       Curses TUI and view models
  df_fintech_term/tools/ Market-data tools, calculators, and daemon controls
  backend/               Scheduled workers and deterministic research actions
packages/
  alpaca-account-api/   Importable Alpaca Trading API wrapper
  alpaca-data/          Importable market-data and streaming toolkit
  technical-indicators/ Dependency-free indicator package
standalone/             Small standalone utilities
notes/                  Design and operating notes
```

## Install and start

```bash
cd DF-FinTechTerm
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt

export APCA_API_KEY_ID='...'
export APCA_API_SECRET_KEY='...'
export NEWSDATA_API_KEY='...'          # optional second news source
./run.sh
```

The TUI requires an 80×20 or larger terminal. Optional integrations are:

- Ollama at `127.0.0.1:11434` for the fixed-model Chat tab;
- `tickrs` on `PATH` for the full-screen industry chart interface;
- `METALPRICE_API_KEY` for silver pricing; and
- `SEC_USER_AGENT="Name email@example.com"` for SEC industry population.

To use real Alpaca trading deliberately, export `ALPACA_LIVE=true`. The UI
changes its mode banner and requires both normal order confirmation and the
literal `LIVE` acknowledgement.

## Terminal walkthrough

The screen has three independent regions.

### Left: main views

`Shift-Tab` cycles:

- **Dashboard** — equity, cash, buying power, positions, and recent orders.
- **Ticker** — live quote table for the persisted personal watchlist.
- **Industry** — Alpaca's U.S. equity universe grouped by SEC SIC industry;
  press `t` to open the selected group in `tickrs`.
- **Live TA** — recently traded daemon subscriptions with RSI, ADX, MACD, OBV,
  ADL, Aroon, and stochastic values recalculated after each trade.

### Right: information and watchlist

`Tab` cycles:

- **News** — one deduplicated feed from Alpaca and NewsData.io.
- **Chat** — an in-memory conversation with the model hard-coded in
  `df_fintech_term/local_llm.py`; news is never sent to the model.
- **Watchlist** — the editor for the exact `stream_watchlist` table consumed by
  the live order-book daemon. Press `+` to add, `d` to remove, or `w` to open
  this tab directly. A running daemon restarts and resubscribes after changes.

### Bottom: trade ticket

The full-width Trade Ticket remains visible below both panels:

- `b` buys any Alpaca-supported symbol;
- `s` only permits symbols currently held with positive quantity;
- `c` cancels an open order; and
- `x` closes a position.

Zero, absent, and short positions are rejected locally by the Sell flow before
an order reaches Alpaca.

Other global keys are `f` for the Finance Tools palette, `Enter` to prompt Chat,
arrow keys or `j`/`k` to navigate, and `q`/Escape to quit.

## Personal watchlist and live daemon

There is one watchlist shared by the Ticker view, Watchlist editor, snapshot
poller, and streaming daemon. Manage it in the TUI or directly:

```bash
./df-fintechterm alpaca stream add AAPL --class stock
./df-fintechterm alpaca stream add BTC/USD --class crypto
./df-fintechterm alpaca stream list
./df-fintechterm alpaca stream start
./df-fintechterm alpaca stream status
```

The daemon stores trades, stock top-of-book quotes, crypto order books, raw
events, news, and latest technical-analysis snapshots in SQLite. It never
submits trades.

## Historical data

Download one series explicitly:

```bash
./df-fintechterm alpaca history AAPL --class stock --timeframe 1Min --start 2024-01-01
```

Advance every distinct series already in the database through Alpaca's API-safe
edge (UTC now minus 15 minutes):

```bash
./df-fintechterm alpaca update-history
```

The incremental updater preserves asset class, timeframe, feed/location, and
adjustment; overlaps the latest bar for idempotent upserts; and continues past
individual failures. The supplied persistent `df-fintechterm-history-update.timer` runs it
daily and catches up after downtime when enabled.

## Industries

Populate the Industry view from Alpaca's complete active U.S. equity catalog:

```bash
export SEC_USER_AGENT="Name email@example.com"
./df-fintechterm classify populate-alpaca
```

The operation is resumable. Issuers receive SEC SIC classifications; ETFs and
other securities without SIC data remain visible under **Unclassified Alpaca
Securities** rather than receiving a guessed industry.

## News retention

Alpaca WebSocket news and periodically polled NewsData.io articles share one
live feed. The supplied hourly `df-fintechterm-news-retention.timer` removes
articles older than seven days from SQLite and, when `DATABASE_URL` is
configured, the PostgreSQL news archive.

## Services and research actions

Services are database-writing workers intended for supervision or scheduling.
Actions are finite, user-requested research jobs.

```bash
./run.sh services
./run.sh service NAME [ARGS]
./run.sh actions
./run.sh action NAME [ARGS]
./run.sh catalog                       # machine-readable JSON
```

Current services cover minute/daily market ingestion, raw news ingestion and
retention, Form 4 ingestion, and deterministic watchlist scoring. Current
actions build candidate packets, backtest insider events, and run the frozen
deterministic QUANT benchmark.

The Finance Tools palette (`f`) exposes these plus historical ingestion, stream
controls, classifications, Tickrs/Ticker launchers, price tools, indicators,
calculators, and diagnostics. The same catalog is available at the command line:

```bash
./df-fintechterm help
./df-fintechterm doctor
```

## Storage and safety

- SQLite holds local assets, bars, watchlists, streams, books, news, and current
  indicator snapshots.
- PostgreSQL is used by the larger research and ingestion pipeline when
  `DATABASE_URL` is configured.
- Raw observations remain separate from derived analysis.
- News and Chat are independent. Sentiment analysis is an explicit user command
  that sends selected stored articles to the configured local Ollama instance;
  it never feeds autonomous scoring or order execution.
- `.env` files, credentials, databases, WAL/SHM files, generated data, and
  personal spreadsheets must not be committed and are covered by `.gitignore`.

The stream controller stores private runtime credentials, when needed, in
`~/.config/df-fintechterm/alpaca.env` with restrictive permissions.

## Reusable packages

Install packages independently from the repository root:

```bash
python -m pip install ./packages/alpaca-account-api
python -m pip install ./packages/alpaca-data
python -m pip install ./packages/technical-indicators
```

The technical-indicators package uses only the Python standard library. Package
specific APIs and examples are documented in each package's README.

## Tests

```bash
cd DF-FinTechTerm
python3 -m unittest discover -s tests -v

cd backend
python3 -m unittest discover -s tests -v
```
