---
tags:
  - finance
  - market-data
  - order-book
  - sqlite
  - alpaca
---

# Live Order Book Collection

The live order-book tool is the real-time market-data layer of the
[[Finance Suite]]. One background daemon reads its desired symbols from SQLite,
connects to Alpaca's WebSocket feeds, stores incoming trades and book-related
events, and continually updates a current book snapshot for each watched
symbol.

It is a **read-only market-data collector**. It never submits, changes, or
cancels orders.

## Role in the finance system

```text
SQLite `stream_watchlist`
            ↓
one persistent systemd user service
            ↓
Alpaca stock / crypto / news WebSockets
            ↓
raw events + trades + current books + articles
            ↓
shared finance SQLite database
            ↓
live CLI / symbol discovery / news / later analysis
```

The collector provides the system's immediate view of market activity:

- Historical bars describe past price windows.
- Live trades describe executions arriving now.
- Live stock quotes describe the current best bid and ask.
- Live crypto order-book messages build a multi-level bid/ask view.
- Live news provides new article context for watched symbols.

All of these layers share one database but use separate tables and semantics.
The daemon does not create historical candles from live events, and adding a
symbol to the live watchlist does not automatically fetch historical bars.

## Important depth distinction

The term “order book” describes two different feed capabilities here:

| Asset class | Alpaca subscription | Stored book |
| --- | --- | --- |
| Stock | Quotes | Top of book only: best bid and best ask |
| Crypto | Order-book updates | Reconstructed full-depth bids and asks |

For stocks, `live_orderbooks` is a convenient normalized representation of the
latest quote. It is not a complete exchange depth-of-book feed. The
`is_full_depth` field makes this distinction explicit.

## Watchlist-driven daemon

The desired subscription set lives in `stream_watchlist`, rather than being
hard-coded into a shell command or separate process per symbol.

Add symbols:

```bash
fsh alpaca stream add AAPL --class stock --feed iex
fsh alpaca stream add MSFT --class stock --feed iex
fsh alpaca stream add BTC/USD --class crypto --location us
```

Inspect or remove them:

```bash
fsh alpaca stream list
fsh alpaca stream remove AAPL --class stock
fsh alpaca stream remove BTC/USD --class crypto
```

Each watchlist row records:

- Asset class.
- Normalized symbol.
- Stock feed or crypto location.
- Time added.

Its composite key permits the same symbol to be represented by distinct source
configurations where supported.

Adding or removing a symbol restarts the daemon only when it is already
running, allowing it to reload the complete watchlist. A stopped daemon remains
stopped until explicitly started.

## Service controls

```bash
fsh alpaca stream start
fsh alpaca stream status
fsh alpaca stream restart
fsh alpaca stream stop
```

Starting the collector:

1. Refuses to start with an empty watchlist.
2. Loads Alpaca credentials from the environment or persistent credential
   file.
3. Installs/reloads one systemd user unit.
4. Enables and starts that unit for the user session.

The intended unit is `fsh-alpaca-stream.service`. It restarts after failures
and writes errors to the user journal:

```bash
journalctl --user -u fsh-alpaca-stream.service -f
```

The current unit contains host-specific paths, including its Python
interpreter. Those paths must be verified if the project is moved or rebuilt.

## Connection grouping

At startup, the daemon groups watchlist rows by:

```text
asset class + feed + location
```

It opens one WebSocket task for each required group and subscribes every symbol
in that group over the same connection. This avoids the earlier design of one
background process per symbol.

It also opens a news WebSocket subscription for the normalized union of all
watchlist symbols.

If a connection fails:

- The error is written to stderr/journald.
- The connection is closed cleanly.
- The daemon waits with exponential backoff, beginning at one second and
  increasing to a maximum of sixty seconds.
- It reconnects, authenticates, and resubscribes.

The service-level restart policy handles process failures, while connection
loops handle ordinary network/API disconnections inside the process.

## Incoming message flow

After Alpaca authenticates the socket, the daemon subscribes to:

- Trades for every symbol.
- Quotes for stocks.
- Order-book updates for crypto.
- News for the normalized watchlist symbol set.

Recognized market messages are committed to SQLite in batches as WebSocket
frames arrive.

### Stock quotes

Each quote contains the current bid price/size/exchange and ask
price/size/exchange. The daemon stores these as one bid and one ask, replacing
the previous current snapshot for that symbol/feed.

### Crypto books

The daemon maintains an in-memory bid and ask map for every crypto symbol:

- A reset message clears the prior reconstructed state.
- A nonzero level inserts or replaces that price.
- A zero-sized level deletes that price.
- Bids are sorted from highest to lowest.
- Asks are sorted from lowest to highest.

After every update, the resulting complete reconstructed snapshot is written to
`live_orderbooks`.

Because reconstruction state is in memory, a reconnect depends on Alpaca
delivering an appropriate reset/snapshot before subsequent deltas can be
treated as a complete book. Consumers should pay attention to timestamps and
feed behavior rather than treating every stale row as currently valid.

## Database tables

The shared database is:

```text
/home/guyyatsu/Finance-Tools/current/DF-FinTechTerm/finance-shell/data/alpaca.sqlite3
```

### `stream_watchlist`

This is desired configuration, not received market data. It is the source of
truth for which streams the daemon should subscribe to after startup.

### `live_market_events`

This is the append-oriented raw event history for:

- Trades (`t`).
- Stock quotes (`q`).
- Crypto order-book updates (`o`).

Each row includes asset class, symbol, event type, feed/location, market
timestamp, receive timestamp, and the original JSON. An event ID is generated
by hashing its source identity and normalized raw JSON. Exact replays after
reconnection are ignored.

This table preserves the event stream needed for auditing, replay research, or
future reconstruction work. It can grow continuously and therefore needs disk,
retention, and backup planning.

### `live_trades`

Trades are also stored in a normalized table containing:

- Trade ID and market timestamp.
- Price and size.
- Exchange, tape, and conditions when available.
- Taker side when available.
- Feed/location, receive time, and original JSON.

The composite key deduplicates matching trades for the same asset, symbol,
timestamp, source, and location.

### `live_orderbooks`

This is the latest-state table. Its primary key is:

```text
asset_class + symbol + feed + location
```

Each new quote or reconstructed crypto update replaces the prior row for that
source. The table stores:

- Market timestamp.
- JSON bid levels.
- JSON ask levels.
- Whether the data is full-depth.
- Local receive timestamp.
- Raw message JSON responsible for the latest update.

Unlike `live_market_events`, this table does not retain every historical book
snapshot. It answers “what is the most recently known book?” while the event
table answers “what messages arrived?”

### News tables

The same daemon writes real-time articles to `news_articles` and maps their
symbols through `news_article_symbols`. Existing article IDs are updated when
system.

## Terminal viewer

Overview of every current stored book:

```bash
fsh alpaca stream view
```

Detailed symbol view:

```bash
fsh alpaca stream view BTC/USD --class crypto --depth 20 --interval 0.5
```

One noninteractive frame:

```bash
fsh alpaca stream view AAPL --class stock --once
```

The viewer opens SQLite in read-only mode and refreshes independently of the
collector. It displays:

- Best bid and ask for all symbols.
- Data age based on local receive time.
- Top-of-book or bid/ask depth counts.
- Detailed bid/ask levels for one symbol.
- Recent normalized trades.
- Recent raw event types and timestamps.

The viewer does not connect to Alpaca and does not modify the database. It is a
live view of what the daemon has already committed.

## Relationship with other Finance Suite tools

- `tickrs` and `ticker` can discover symbols from live trades, order books, or
  event rows even when historical bars are absent.
- The news commands read articles gathered by the same daemon.
- Industry classification can use symbols that have actual historical or live
  market records.
- Historical collection remains independently operator-triggered.
- Future indicators may combine historical bars with current trades/books, but
  must account for different time semantics and feed quality.

The shared SQLite database is therefore both an integration boundary and a
decoupling mechanism: the long-running writer can operate independently while
terminal tools and analysis commands read durable state.

## WAL, concurrency, and backups

SQLite uses WAL mode so the daemon can continue writing while readers inspect
the database. During active use, `alpaca.sqlite3-wal` and
`alpaca.sqlite3-shm` are part of database state.

- Do not copy only the main `.sqlite3` file while the writer is active.
- Use a SQLite-aware backup or stop/checkpoint the writer first.
- Monitor WAL and event-table growth.
- Avoid long write transactions in analysis tools.
- Treat raw market events and news as potentially high-growth data.

## Inspection queries

Current book freshness:

```bash
sqlite3 ~/Finance-Tools/current/DF-FinTechTerm/finance-shell/data/alpaca.sqlite3 '
SELECT asset_class, symbol, feed, location, timestamp, received_at,
       is_full_depth
FROM live_orderbooks
ORDER BY asset_class, symbol;'
```

Event volume by symbol and type:

```bash
sqlite3 ~/Finance-Tools/current/DF-FinTechTerm/finance-shell/data/alpaca.sqlite3 '
SELECT asset_class, symbol, event_type, count(*)
FROM live_market_events
GROUP BY asset_class, symbol, event_type
ORDER BY asset_class, symbol, event_type;'
```

Recent trades:

```bash
sqlite3 ~/Finance-Tools/current/DF-FinTechTerm/finance-shell/data/alpaca.sqlite3 '
SELECT asset_class, symbol, timestamp, price, size, taker_side
FROM live_trades
ORDER BY timestamp DESC
LIMIT 20;'
```

## Operational considerations

- Credentials belong in `~/.config/finance-shell/alpaca.env` with mode `0600`,
  not in the database or vault.
- Feed availability and depth depend on Alpaca subscription/entitlements.
- A running process does not prove data is fresh; inspect receive age.
- A stored current row can remain after a disconnect and become stale.
- Watch journal errors for authentication, entitlement, malformed data, and
  reconnect loops.
- Adding many symbols increases traffic, storage growth, and news volume.
- Raw event retention should be defined before unbounded long-term operation.
- Market data should not be treated as guaranteed complete or suitable for
  unattended trading decisions.
- The tool observes markets only; execution would require a separate,
  deliberately designed and authorized system.

## Current limitations and likely improvements

- Stock data is top-of-book only, despite the normalized order-book name.
- Current book snapshots have no explicit stale/connected flag.
- Crypto reconstruction state is not persisted independently of the latest
  snapshot and is rebuilt after process start/reconnect.
- Watchlist changes require a daemon restart rather than dynamic subscription
  changes.
- Raw events have no configured retention/aggregation policy.
- There is no stored connection/run history comparable to historical
  `fetch_runs`.
- Per-symbol freshness, disconnect, gap, and data-quality alerts would improve
  operational visibility.

## Related notes

- [[Finance Suite]]
