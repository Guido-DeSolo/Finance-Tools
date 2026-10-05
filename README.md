# Finance Tools

Version **0.0.1**

`df-fintechterm` combines Finance-Tools and DF-FinanceTerminal as one CLI for
Alpaca accounts, market data, personal assets, and research. The interface is
plain commands and JSON/text output. Orders use Alpaca paper trading by default;
live orders require `--live` and the exact confirmation `LIVE`.

## Install

```sh
cd DF-FinTechTerm
python3 -m venv .venv && . .venv/bin/activate
python -m pip install -r requirements.txt
export APCA_API_KEY_ID=… APCA_API_SECRET_KEY=…
./df-fintechterm help
```

The launcher also reads `~/.config/df-fintechterm/alpaca.env`. Set
`FINANCE_DB_FILE` (or `ALPACA_DATA_DB`) to move the shared market/news/wealth SQLite database,
`DF_LEDGER_DB` to move the order audit ledger, and `DATABASE_URL` to enable the
PostgreSQL research pipeline. Optional keys: `NEWSDATA_API_KEY` adds a news
source, `METALPRICE_API_KEY` prices silver, and `SEC_USER_AGENT` enables SEC
company classification. Local LLM jobs use Ollama at `127.0.0.1:11434`.

## User functionality

Every user-facing command is listed below. Run any command with `--help` for
its arguments; `df-fintechterm services`, `actions`, and `catalog` list the
scheduled jobs and research actions.

| Area | Command | What it does |
| --- | --- | --- |
| Alpaca account | `df-fintechterm account` or `orders account` | Show account details and positions. |
| Orders | `orders buy|sell SYMBOL --quantity N` or `--notional USD` | Preview risk, confirm, submit market/limit/stop orders, and record each decision/result in the hash-chained ledger. Add `--live` before the subcommand for live trading; live confirmation cannot be skipped. |
| Orders | `orders list [--limit N]`, `orders cancel ID`, `orders close SYMBOL [--percentage N]` | Review orders, cancel an order, or close some/all of a position, with confirmation and audit records. |
| Order stream | `orders watch` | Print live account order updates as JSON. |
| Audit | `ledger verify` or `ledger export --output FILE` | Verify ledger integrity or export events as JSONL. |
| Asset catalog | `alpaca sync-assets [--status active|inactive|all]` | Save Alpaca's stock/crypto asset catalog locally. |
| Price history | `alpaca history SYMBOLS --class stock|crypto ...` | Download historical Alpaca bars to SQLite, with timeframe, date range, feed, adjustment, and pagination controls. |
| History maintenance | `alpaca update-history`; `alpaca history-list` | Incrementally update stored series or list them. |
| Local data | `alpaca status`, `alpaca news [SYMBOL]`, `alpaca timeframes` | Show local row counts, inspect stored news, or list supported history windows. |
| Personal net worth | `wealth show`, `wealth refresh` | Show the balance sheet or refresh Bitcoin, stock, cash, equipment, and silver valuations from Alpaca and the configured metal-price service. |
| Equipment | `wealth equipment import FILE.ods`, `wealth equipment add NAME PRICE` | Import a two-column ODS inventory or add equipment manually. |
| Silver | `wealth silver buy OUNCES AMOUNT`, `wealth silver sell OUNCES PROCEEDS` | Track physical silver purchases and sales, FIFO cost basis, remaining ounces, and realized profit/loss. `--at` records a transaction timestamp. |
| Live market collector | `alpaca stream add|remove SYMBOL --class stock|crypto`, `list`, `start`, `stop`, `restart`, `status` | Maintain one stock/crypto watchlist and control its systemd user service. It stores trades, quotes/order books, news, and technical snapshots; it never places orders. |
| Live analysis | `alpaca analysis ...` | Inspect stored active subscriptions and technical-analysis snapshots. The live collector calculates RSI, ADX, MACD, OBV, ADL, Aroon, and stochastic indicators as trades arrive. |
| Indicators | `indicators report`, `indicators example` | Calculate/display RSI, ADX, MACD, OBV, ADL, Aroon, and stochastic values from stored bars or a built-in example. |
| Prices | `price bitcoin`, `price silver` | Fetch current Bitcoin or silver reference prices. |
| Classification | `classify ...` | Populate and inspect Alpaca assets classified by SEC SIC industry, leaving assets without a classification explicitly unclassified. |
| News ingestion | `service news-ingest` | Collect Alpaca and optional NewsData.io stories into the shared database. |
| News curation | `news curate SYMBOL [--output FILE]` | Write matching stored news into an LLM-ready text file. |
| News sentiment | `sentiment ...` | Run explicit local-model sentiment analysis over selected stored stories. |
| Insider activity | `insiders latest [--refresh] [--json]`, `insiders screener` | Fetch/cache homepage filings or query the fixed recent insider-trade screener. |
| Form 4 data | `service insider-ingest`; `action insider-backtest` | Ingest normalized SEC Form 4 activity and run the insider-event study. |
| Calculators | `calc compound PRINCIPAL RATE YEARS [MONTHLY]`, `calc gain COST VALUE`, `calc budget INCOME [EXPENSE ...]`, `calc allocate TOTAL WEIGHT ...` | Calculate compound growth, gain/return, budget/savings rate, or weighted allocation. |
| Local LLM | `llm ask PROMPT` | Send a one-shot prompt to the configured local Ollama model. |
| Watchlist research | `action candidate-packets`, `action watchlist-fundamental` | Build validated candidate packets or publish local-LLM research for stream-watchlist symbols. |
| Daily research | `action daily-research` | Publish a validated local-LLM daily research notebook. |
| Quant research | `action benchmark-quant-v2`, `action portfolio-replay`, `action execution-analysis` | Run the frozen deterministic signal benchmark, replay explicit trade plans with costs, or import fills and assess execution quality. |
| Alerts | `action alert-manage add|list|remove|scan|test ...` | Manage threshold rules for price/indicator metrics and send Discord/Telegram alerts. |
| Background jobs | `services`, `service NAME` | List/run `market-minute`, `market-daily-iex`, `market-daily-sip`, `news-ingest`, `news-retention`, `alert-scan`, `insider-ingest`, and `watchlist-refresh`. |
| Research actions | `actions`, `action NAME` | Run `candidate-packets`, `daily-research`, `alert-manage`, `insider-backtest`, `benchmark-quant-v2`, `portfolio-replay`, `execution-analysis`, `ledger-audit`, or `watchlist-fundamental`. |
| Health | `doctor` | Check core Python dependencies and backend command catalog availability. |

Typical commands:

```sh
./df-fintechterm alpaca history AAPL MSFT --class stock --timeframe 1Day --start 2025-01-01
./df-fintechterm wealth refresh
./df-fintechterm alpaca stream add AAPL --class stock
./df-fintechterm alpaca stream start
./df-fintechterm orders buy AAPL --notional 25
./df-fintechterm ledger verify
```

## Data and safety

SQLite stores market history, the stream watchlist and observations, news,
personal wealth, and derived analysis. PostgreSQL supports the larger research
pipeline when configured. Services ingest data and deliver configured alerts;
they do not trade. Sentiment, news curation, and research are explicit jobs.
Never commit credentials, `.env` files, databases, generated data, or personal
spreadsheets.

## Development

The Python package and scheduled backend live under `DF-FinTechTerm/`. The
standalone API, market-data, indicator, risk, and ledger modules are reusable
without a screen interface. See the backend's `services`, `actions`, and
`catalog` output for the exact job registry.
