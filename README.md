# Finance Tools

A consolidated collection of local finance and market-data utilities. This
repository contains tools and supporting documentation only: credentials,
environment files, databases, generated market data, caches, and personal
asset spreadsheets are intentionally excluded.

## Repository map

```text
current/
  finance-shell/          Market-data collection and terminal analysis suite
  dixie-alpaca-terminal/  Curses-based Alpaca account and trading terminal
packages/
  alpaca-account-api/     Complete account and trading API wrapper
  alpaca-data/            Importable Alpaca data and SQLite collection package
  technical-indicators/  Importable, dependency-free indicator package
standalone/
  alpaca_history.py       Standalone Alpaca-to-SQLite history ingester
legacy/
  laptop/                 Earlier research and technical-analysis utilities
  removable-drive/        Earlier spot-price and indicator utilities
notes/                    Architecture and operating notes
```

## Current tools

### Alpaca account and trading API

`packages/alpaca-account-api` provides dependency-free one-to-one coverage of
all currently documented Alpaca retail Trading API operations, including
orders, positions, account activity, portfolio history, options, locates,
tokenization, crypto wallets, watchlists, and activity events. Paper mode is
the default. Install it with:

```bash
python -m pip install ./packages/alpaca-account-api
```

### Alpaca data package

`packages/alpaca-data` packages the reusable Alpaca data functionality: asset
catalogs, historical bars, snapshots, latest quotes/trades, crypto order books,
live WebSocket collection, SQLite persistence, stored-data views, news,
sentiment, and symbol classification. Install it with:

```bash
python -m pip install ./packages/alpaca-data
```

### Dependency-free technical indicators

`packages/technical-indicators` is a standalone Python package providing OBV,
ADX, ADL, Aroon, MACD, RSI, and stochastic oscillators. It uses only the Python
standard library and can be installed into another project with:

```bash
python -m pip install ./packages/technical-indicators
```

### Finance Shell

`current/finance-shell/fsh` is the main dispatcher. It collects historical and
live Alpaca market data, displays stored market state, analyzes news with a
local Ollama model, classifies symbols, retrieves spot prices, and provides
basic finance calculators. See its own README for commands and dependencies.

### Dixie Alpaca Terminal

`current/dixie-alpaca-terminal` is a terminal UI for Alpaca account data,
quotes, news, and trading. Paper mode is the default. Configure credentials in
the process environment; no environment file is included in this repository.

### Standalone history ingester

`standalone/alpaca_history.py` downloads Alpaca bars into a user-selected local
SQLite database. The resulting database is ignored by Git.

## Security and data policy

Never commit API credentials, `.env` files, key files, database files, or
database WAL/SHM sidecars. The ignore rules cover the common forms, but inspect
the staged set before every commit.

The tools expect credentials such as `APCA_API_KEY_ID`,
`APCA_API_SECRET_KEY`, `NEWSDATA_API_KEY`, and `METALPRICE_API_KEY` to be
provided through the environment or through the documented local credential
location.
