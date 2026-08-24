# DF-FinTechTerm capability rundown

Snapshot: 2026-08-24

This is portable context for external review. Repository: `Finance-Tools`.
Application root: `current/DF-FinTechTerm`.

## Product boundary

DF-FinTechTerm is one application. The terminal and Finance Shell are
user-facing; services collect or derive information in the background; actions
are finite operations explicitly initiated by a user.

News and LLM chat are independent. No news is sent to an LLM, classified for
sentiment, synthesized by a model, or used in model benchmarks.

## Services

The Alpaca WebSocket daemon streams trades, stock quotes, crypto order books,
and Alpaca news for a persisted watchlist. It reconnects automatically, stores
deduplicated raw and normalized records in SQLite, and recalculates OBV, ADX,
ADL, Aroon, MACD, RSI, and stochastic values after every applicable trade.

Scheduled PostgreSQL services:

| Name | Capability |
|---|---|
| `market-minute` | Paginated Alpaca one-minute IEX bar ingestion |
| `market-daily-iex` | Batched adjusted daily IEX ingestion |
| `market-daily-sip` | Batched adjusted daily SIP ingestion |
| `news-ingest` | Raw Alpaca news ingestion |
| `news-retention` | Hourly pruning of news older than seven days |
| `insider-ingest` | Normalized Form 4 ingestion |
| `watchlist-refresh` | Deterministic candidate scoring |

## Actions

| Name | Capability |
|---|---|
| `candidate-packets` | Build and validate ranked evidence packets |
| `insider-backtest` | Run the insider-event forward-return study |
| `benchmark-quant-v2` | Run the frozen deterministic QUANT benchmark |

Finance Shell also provides historical Alpaca ingestion, asset sync, stored-data
status, live stream watchlist management, live book/trade rendering, SEC SIC
classification, Tickrs/Ticker launchers, Bitcoin and silver prices, technical
indicator tests/reports/examples, and deterministic financial calculators.

## Unified live news

The right panel reads Alpaca WebSocket news and periodically polled NewsData.io
results collected by the live daemon. Both sources are normalized,
deduplicated by URL or headline, sorted newest-first, labeled by provider and
source, and rendered as one scrolling feed. Either source can continue supplying
the panel when the other is unavailable.

The Chat tab remains a user-driven conversation with one hard-coded local Ollama
model. It has no connection to the news feed.

## Terminal and packages

The TUI provides account values, positions, orders, watched quotes, merged news,
chat, live technical analysis, order entry, cancellation, position closing, and
the complete tool palette. Its independent main-area tabs include the dashboard,
an SEC-industry browser with live constituent snapshots, and technical analysis.
The independent right pane remains visible beside every main view and separately
toggles between News and Chat. Paper trading is the
default and live operations require explicit confirmation.
The Industry tab launches the real `tickrs` chart/summary TUI for the selected
industry's exact constituent set and restores DF-FinTechTerm when it exits.
Its resumable population action synchronizes Alpaca's full active U.S. equity
catalog, applies SEC SIC classifications, and retains non-SIC securities in an
explicit unclassified bucket so catalog coverage is complete.

Reusable packages provide 57 Alpaca Trading API operations, Alpaca market-data
REST/WebSocket collection and SQLite persistence, plus dependency-free OBV, ADX,
ADL, Aroon, MACD, RSI, and stochastic indicators.

## Storage and limits

SQLite stores local market streams, raw news, books, trades, watchlists, and
indicator snapshots. PostgreSQL stores historical bars, raw news, insider data,
and deterministic research scores. Current schemas create no sentiment or model
analysis tables; legacy tables in existing databases are left untouched.
The news-retention worker limits both configured news stores to the latest seven
days without pruning any market-history tables.

Chat is the only LLM integration. There is no autonomous signal-to-order loop.
Fees, slippage, portfolio sizing, risk enforcement, replay, counterfactual
evaluation, and an immutable decision ledger remain future work.
