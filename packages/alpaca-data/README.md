# Alpaca data

An importable Python package for Alpaca market-data access, collection,
persistence, and local analysis. Trading and order placement are deliberately
outside this package.

## Included functionality

- Read-only REST client for assets, stock snapshots, latest stock quotes and
  trades, crypto snapshots, and crypto order books
- Paginated historical stock and crypto bars
- SQLite schema and idempotent storage for assets, bars, fetch runs, live
  trades, quotes, order books, raw market events, and Alpaca news
- Stock, crypto, and news WebSocket collection with reconnect handling
- Stored stream rendering and watchlist helpers
- SEC industry classification for stored symbols
- Local Ollama sentiment analysis for stored Alpaca news

The base package uses only the Python standard library. Live WebSocket
collection is optional and requires `websockets`.

## Install

From the root of `Finance-Tools`:

```bash
python -m pip install ./packages/alpaca-data
```

To include live streaming support:

```bash
python -m pip install './packages/alpaca-data[stream]'
```

## Credentials

Pass credentials directly or set them in the process environment:

```bash
export APCA_API_KEY_ID='your-key-id'
export APCA_API_SECRET_KEY='your-secret-key'
```

No credentials or environment files are stored by this package.

## REST usage

```python
from alpaca_data import MarketDataClient

client = MarketDataClient.from_environment()
snapshots = client.stock_snapshots(["AAPL", "MSFT"])
quotes = client.latest_stock_quotes(["AAPL"])
books = client.crypto_orderbooks(["BTC/USD"])
bars = client.historical_bars("AAPL", start="2025-01-01", timeframe="1Day")
news_page = client.news(["AAPL", "MSFT"], limit=20)
```

Every convenience method returns the symbol-keyed dictionary from Alpaca. For
other read-only endpoints, use `client.get(base_url, path, params)`.

## SQLite storage usage

```python
from pathlib import Path
from alpaca_data import connect

database = connect(Path("market-data.sqlite3"))
rows = database.execute(
    "SELECT timestamp, close FROM bars WHERE symbol=? ORDER BY timestamp",
    ("AAPL",),
).fetchall()
```

If no database path is supplied to the command helpers, the default is
`~/.local/share/finance-tools/alpaca.sqlite3`. Set `ALPACA_DATA_DB` to choose a
different default. Database files are runtime data and must not be committed.

Additional modules are available for focused imports:

```python
from alpaca_data import store, stream, view, sentiment, classification, industry
```

## Test

```bash
cd packages/alpaca-data
python -m unittest discover -s tests -v
```
