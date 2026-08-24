---
aliases:
  - Finance Shell
  - Market Data Suite
tags:
  - finance
  - market-data
  - alpaca
  - sqlite
status: active
---

# Finance Suite

Finance Shell is the local command center for collecting, inspecting, and
analyzing market data. It lives at:

```text
/home/guyyatsu/Finance-Tools/current/DF-FinTechTerm/finance-shell
```

The complete operator guide is
`/home/guyyatsu/Finance-Tools/current/DF-FinTechTerm/finance-shell/README.md`. This note is the short
working reference.

## What it does

- Downloads historical stock and crypto bars from Alpaca.
- Batch-downloads complete one-minute stock history from a symbol file.
- Runs one background daemon for live trades, quotes, crypto order books, and
  real-time Alpaca news.
- Saves raw incoming events and derived current-book state in SQLite.
- Shows live order books and recent trades in the terminal.
- Classifies stocks by SEC SIC industry and broad sector.
- Opens Tickrs for every stored symbol or for a selected industry.
- Opens Ticker with every symbol that contains stored market data.
- Provides technical-indicator validation, simple prices, and calculators.

The suite does **not** place market orders.

## Data flow

```text
Alpaca historical API ────────> bars ──────────────┐
                                                    │
Alpaca market WebSockets ─────> live events/books ─┼─> alpaca.sqlite3
                                                    │
Alpaca news WebSocket ─────────> news articles ─────┤
                                                    │
SEC company data ──────────────> industry tags ─────┤
                                                    │
```

## Start a terminal session

```bash
cd /home/guyyatsu/Finance-Tools/current/DF-FinTechTerm/finance-shell
source activate.bash
fsh doctor
fsh alpaca status
```

## Credentials

Persistent Alpaca credentials belong in:

```text
~/.config/finance-shell/alpaca.env
```

Required assignments:

```bash
APCA_API_KEY_ID="..."
APCA_API_SECRET_KEY="..."
```

The file must be private:

```bash
chmod 600 ~/.config/finance-shell/alpaca.env
```

Never put credentials in this vault, the finance database, or source control.

SEC classification uses a contact-bearing user agent:

```bash
export SEC_USER_AGENT="Your Name your-email@example.com"
```

## Historical data

See [[Historical Market Data Collection]] for the collector's architecture,
database schema, pagination behavior, batch rules, operational role, and
limitations.

Daily stock bars:

```bash
fsh alpaca history AAPL --class stock --timeframe 1Day --start 2020-01-01
```

Complete available one-minute history:

```bash
fsh alpaca history AAPL --class stock --timeframe 1Min --start 1970-01-01 --feed iex
```

One symbol per line batch:

```bash
fsh alpaca history-list symbols.txt
```

The batch command skips symbols when any stock bars already exist, including
partial downloads.

## Live collector

See [[Live Order Book Collection]] for the daemon architecture, watchlist,
stock-versus-crypto depth behavior, database tables, reconstruction logic,
terminal viewer, and operational limitations.

Manage the watchlist:

```bash
fsh alpaca stream add AAPL --class stock --feed iex
fsh alpaca stream add BTC/USD --class crypto --location us
fsh alpaca stream list
fsh alpaca stream remove AAPL --class stock
```

Control the background service:

```bash
fsh alpaca stream start
fsh alpaca stream status
fsh alpaca stream restart
fsh alpaca stream stop
```

Watch its journal:

```bash
journalctl --user -u fsh-alpaca-stream.service -f
```

Watch live books in the CLI:

```bash
fsh alpaca stream view
fsh alpaca stream view BTC/USD --depth 20 --interval 0.5
```


## Industry and Tickrs

```bash
fsh classify refresh
fsh classify list
fsh tickrs
fsh tickrs-industry
fsh ticker
```

`fsh tickrs` derives its symbols from rows that actually contain market data.
`fsh tickrs-industry` presents an interactive industry selector and requires
stored SEC classifications.
`fsh ticker` builds a fresh database-derived `--watchlist` for the installed
Ticker terminal application.

## Useful database locations and tables

Database:

```text
/home/guyyatsu/Finance-Tools/current/DF-FinTechTerm/finance-shell/data/alpaca.sqlite3
```

Important tables:

| Table | Purpose |
| --- | --- |
| `bars` | Historical OHLCV bars |
| `fetch_runs` | Historical download status and errors |
| `stream_watchlist` | Desired live subscriptions |
| `live_market_events` | Append-only raw trade, quote, and book events |
| `live_trades` | Deduplicated live trades |
| `live_orderbooks` | Current reconstructed books |
| `news_articles` | Real-time Alpaca news |
| `news_article_symbols` | Article-to-symbol links |
| `symbol_classifications` | SEC SIC industries and sectors |

The database uses WAL mode. While active, its `-wal` and `-shm` sidecars are
part of the live database state.

## Other tools

```bash
fsh indicators test
fsh indicators report
fsh price bitcoin
fsh price silver
fsh calc compound 1000 7 10 100
fsh calc gain 1250 1430
fsh calc budget 3200 1200 450 200
fsh calc allocate 1000 60 30 10
```

## Fast troubleshooting

```bash
fsh doctor
fsh alpaca stream status
journalctl --user -u fsh-alpaca-stream.service -n 100 --no-pager
curl http://127.0.0.1:11434/api/tags
```

Related notes: [[Historical Market Data Collection]],
[[Live Order Book Collection]].

Related infrastructure: [[Guyyatsu (DOT) Me Homelab Server System]].
