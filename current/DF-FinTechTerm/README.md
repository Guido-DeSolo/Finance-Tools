# DF-FinTechTerm

DF-FinTechTerm is a keyboard-driven Alpaca trading and research workstation: a
Bloomberg-style workflow built for an ordinary terminal. It combines account
monitoring, guarded order entry, streamed order state, symbol research, local
LLM publications, bot alerts, strategy replay, execution analysis, and a
tamper-evident activity ledger, and a cached OpenInsider filing monitor without
turning model output or third-party summaries into trading authority.

## What we built

1. **Order selection and live updates.** The recent-order table is selectable,
   cancellations act on the selected row, and Alpaca `trade_updates` stream
   fills, partial fills, rejections, and cancellations into the UI. REST polling
   remains the reconciliation fallback.
2. **Pre-trade risk controls.** Every ticket previews notional, projected symbol
   concentration, and remaining buying power. Configured position, notional,
   buying-power, oversell, and daily-loss violations block submission locally.
3. **Command bar and symbol workspace.** `:` accepts terminal-style navigation
   and symbol commands such as `AAPL GO`. A symbol page brings quote, metadata,
   industry, position, orders, stored history, indicators, and news together.
4. **Daily research publishing.** An explicit action assembles validated evidence,
   asks the fixed local Ollama model for a bounded summary, and publishes JSON,
   Markdown, and a self-contained Jupyter notebook. Evidence stays authoritative;
   generated prose does not place orders or create alerts.
5. **Discord and Telegram alerts.** Deterministic price and indicator rules support
   thresholds, crossings, cooldowns, re-arming, multiple bot destinations, and
   retryable delivery records.
6. **Replay and execution analysis.** Portfolio replay evaluates explicit long
   and short plans with visible cost assumptions. Fill analysis imports individual
   Alpaca fills and measures side-adjusted slippage against local market records.
7. **Tamper-evident ledger.** Trading decisions, risk outcomes, submissions,
   cancellation and close requests, and streamed broker lifecycle events are
   appended to a SHA-256 hash chain in SQLite. New orders fail closed if their
   authorization cannot be recorded; de-risking actions remain available.
8. **OpenInsider homepage monitor.** A cached left-panel view shows the homepage's
   latest cluster buys, insider buys, penny-stock buys, large sales, and general
   filings while preserving the site's transaction labels and filing links.

The screen keeps a full-width Trade Ticket below the main and side panes. Buys
accept any Alpaca-supported symbol. Sells are locally restricted to positive
holdings, so zero and short positions are not accidentally treated as sellable.

## Interface layout

- **Left/main pane:** Dashboard, personal ticker, industry browser, live technical
  analysis, symbol workspace, Daily Research, or OpenInsider activity.
- **Right pane:** News, local LLM chat, or the persistent stream watchlist.
- **Bottom panel:** Account risk summary and the paper/live Trade Ticket.
- **Ticker strip:** Latest watched quotes, bid/ask, sizes, and daily change.

The right pane and Trade Ticket remain available while changing the main view.

## Start

Install the root Python requirements first. The embedded industry chart interface
also requires `tickrs` on `PATH`. Backend research, database, and bot jobs use the
separate backend requirements file.

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -r backend/requirements.txt
```

Export credentials as needed; never commit them:

```bash
cd /home/guyyatsu/Finance-Tools/current/DF-FinTechTerm
export APCA_API_KEY_ID='...'
export APCA_API_SECRET_KEY='...'
export NEWSDATA_API_KEY='...'
./run.sh
```

Paper trading is the default. To deliberately use real money, also set `ALPACA_LIVE=true`. Live mode is displayed in red and requires typing both `YES` and `LIVE` before a trading action.

Optional settings:

```bash
export ALPACA_REFRESH_SECONDS=3
export DF_RISK_WARN_POSITION_PCT=20
# Optional hard limits; zero disables each limit.
export DF_RISK_MAX_POSITION_PCT=0
export DF_RISK_MAX_ORDER_NOTIONAL=0
export DF_RISK_MAX_DAILY_LOSS=0
export DF_LEDGER_DB="$HOME/.local/share/df-fintechterm/ledger.sqlite3"
export DF_RESEARCH_OUTPUT_DIR="$HOME/.local/share/df-fintechterm/research"
export DF_OPENINSIDER_CACHE="$HOME/.cache/df-fintechterm/openinsider-homepage.json"
```

The personal watchlist is not configured separately through the TUI. Its single
source of truth is the daemon's `stream_watchlist` table.

Finance Shell is embedded in this application. Use it from the TUI with `f`
or invoke the same dispatcher directly:

```bash
./run.sh fsh help
./run.sh fsh alpaca status
./run.sh fsh alpaca update-history
./run.sh fsh calc gain 1250 1430
./run.sh services
./run.sh actions
```

`services` lists ingestion and scoring workers intended for supervision or
scheduling. `actions` lists finite operations initiated by a user. Run a named
entry with `./run.sh service NAME` or `./run.sh action NAME`.

Useful finite actions include:

```bash
./run.sh action daily-research
./run.sh action portfolio-replay -- --help
./run.sh action execution-analysis -- --help
./run.sh action ledger-audit -- verify
./run.sh action ledger-audit -- export --output ./ledger-export.jsonl
```

Current scheduled/service operations are `market-minute`, `market-daily-iex`,
`market-daily-sip`, `news-ingest`, `news-retention`, `alert-scan`,
`insider-ingest`, and `watchlist-refresh`. Run `./run.sh catalog` for the complete
machine-readable action and service inventory.

A persistent daily systemd timer advances every stored Alpaca bar series through
the current API-safe edge, defined as UTC now minus 15 minutes.

## Keys

- `:`: open the command bar (`AAPL`, `AAPL GO`, `DASH`, `ORDERS`, `WATCH`,
  `TICKER`, `INDUSTRY`, `TA`, `RESEARCH`, or `INSIDERS`)
- `a`: switch between the account dashboard and live technical-analysis view
- `r`: switch between the account dashboard and Daily Research view
- `u`: switch between the account dashboard and OpenInsider homepage view
- `g`: generate a validated local-LLM research publication from the Research view
- `i`: switch between the account dashboard and Industry view
- `Shift-Tab`: cycle Dashboard, Ticker, Industry, and Live TA main views
- `Tab`: cycle the right pane through News, Local Chat, and Watchlist
- `w`: open the right-side Watchlist editor
- `+`: add a stock or crypto subscription from the Watchlist tab
- `d`: remove the selected subscription from the Watchlist tab
- `Enter`: send a Local Chat prompt from any main view
- `t`: open `tickrs` for the selected industry
- `b`: buy any Alpaca-supported symbol
- `s`: sell a symbol from the positive account holdings shown in the Trade Ticket
- `f`: open the complete Finance Shell tool palette
- `o`: focus the recent-orders table; use Up/Down or `j`/`k` to select an order
- `c`: cancel the selected order after confirmation
- `x`: close an entire position
- Up/Down or `j`/`k`: scroll/select the active research, OpenInsider, industry,
  analysis, news, chat, watchlist, or focused-order content
- Page Up/Page Down: scroll Industry constituents or the personal Ticker view
- `q` or Escape: quit

## Fixed local LLM

The Chat tab calls the local Ollama API at `http://127.0.0.1:11434/api/chat`.
It keeps the latest conversation turns in memory for the current TUI session
and performs inference in a background thread so quotes and account refreshes
remain responsive.

The model is intentionally fixed rather than user-selectable. To choose the
specific model later, edit this single constant in
`df_fintech_term/local_llm.py`:

```python
LOCAL_LLM_MODEL = "analyst:latest"
```

The selected model must already be installed in the local Ollama instance. No
chat messages are written to disk by DF-FinTechTerm.

## Finance Shell palette

Press `f`, select a tool with the arrow keys or `j`/`k`, and press Enter. The
palette covers all Finance Shell operations:

- Indicator tests, reports, and deterministic examples
- Bitcoin and silver prices
- Tickrs, Ticker, and industry-oriented Tickrs views
- SEC classification refresh and reports
- One merged live-news panel sourced from Alpaca and NewsData.io
- Alpaca asset sync, historical data, batch history, status, stored news, and
  timeframe help
- Per-trade rolling technical analysis for live-order-book symbols
- Stream watchlist management, daemon controls, status, and live view
- Compound-growth, gain/loss, budget, and allocation calculators
- Finance Shell doctor and help

Tools that need parameters show the expected arguments before prompting. The
TUI constructs an argument vector directly and never invokes a command shell.
Terminal-native tools temporarily take over the display and restore the
originating DF-FinTechTerm view when they finish.

Press `a` for a full-screen view of watched symbols whose order books received
a trade in the last five minutes. Symbols are sorted by their most recent
analysis update. Each entry shows buffer depth plus RSI, ADX, MACD, signal,
histogram, OBV, ADL, Aroon up/down, and stochastic K/D values.

The order form supports market, limit, stop, and stop-limit orders, using quantity or `$`-prefixed notional amounts. Alpaca validates combinations and returns rejection details in the status line.
Before confirmation, the terminal estimates order notional, projected symbol
concentration, and remaining buying power. Concentration warnings are advisory;
configured maximum position, order-notional, daily-loss, and available-buying-power
violations block submission locally in both paper and live modes.

## Command bar and symbol workspace

Press `:` and enter a symbol by itself or with `GO`, `CHART`, `NEWS`, or `TA`.
The symbol workspace combines the latest quote, asset metadata, SEC industry,
account position, open-order count, one consistent stored price series, current
technical indicators, and tagged news. The right-side News/Chat/Watchlist pane
and the fixed Trade Ticket remain available. Navigation commands provide direct
access to the existing views without requiring shortcut memorization.

## Daily research publications

Open `RESEARCH` from the command bar or press `r`, then press `g`. This explicit
action builds validated candidate packets from PostgreSQL, gives a bounded
evidence copy to the fixed local Ollama model, and publishes three local files:
the complete evidence JSON, a Markdown brief, and a Jupyter notebook containing
both the narrative and embedded evidence. The latest report is rendered in the
TUI. Set `DF_RESEARCH_OUTPUT_DIR` to change the publication directory; otherwise
reports remain outside Git under `~/.local/share/df-fintechterm/research`.

News supplied in candidate packets is treated as untrusted reported material.
The prompt forbids invented facts and trade recommendations, but model output
can still be wrong; the embedded deterministic evidence remains authoritative.

## OpenInsider activity

Press `u` or enter `INSIDERS` in the command bar to open the left-panel activity
view. It reads the documented rows from OpenInsider's public homepage, labels
each row by its original homepage section, and caches the response for five
minutes at `~/.cache/df-fintechterm/openinsider-homepage.json`. Override the
location with `DF_OPENINSIDER_CACHE`. If a refresh fails, the last successful
cache remains visible and is marked stale. These are third-party summaries of
SEC filings, not independently verified trade signals or order instructions.
Purchases are green, sales are red, and grants, tax transactions, and other
filing types remain neutral. The cached records retain source filing URLs, though
opening those links is not yet exposed in the interface.

## Data and execution boundaries

- **Alpaca REST:** accounts, positions, reconciliation, quotes, market snapshots,
  assets, and order submission.
- **Alpaca `trade_updates`:** streamed order fills, partial fills, cancellations,
  and rejections.
- **Local SQLite:** streamed market history, analysis snapshots, classifications,
  news, watchlist subscriptions, execution fills, and the separate audit ledger.
- **PostgreSQL backend:** normalized insider records, candidate evidence, scoring,
  and other research datasets.
- **Ollama:** session-only chat and explicit daily research narrative generation.
- **OpenInsider:** cached, read-only homepage summaries; not an order signal.
- **Discord/Telegram:** delivery destinations for deterministic alert rules.

## Bot alerts

The deterministic alert scanner delivers through real Discord or Telegram bot
credentials rather than webhooks. Rules support live price and stored technical
indicators, ordinary thresholds and crossings, per-rule cooldowns, multiple
destinations, re-arming, and retryable delivery records. Manage rules through
`./run.sh action alert-manage ...`; run one scan with
`./run.sh service alert-scan`. See `backend/README.md` for setup and examples.
No LLM output can create an alert or order.

## Replay and execution analysis

The `portfolio-replay` action evaluates explicit long/short trade plans against
one requested stored-bar timeframe. Cost assumptions are visible and
configurable; missing bars are reported as skipped trades. The
`execution-analysis` action imports Alpaca's individual fill activities and
measures side-adjusted slippage against the nearest preceding locally recorded
trade. Unmatched fills remain visibly unmatched rather than receiving a zero
cost. Both actions are available through `./run.sh action ...` and the Finance
Tools action runner.

## Trading activity ledger

The ledger defaults to
`~/.local/share/df-fintechterm/ledger.sqlite3`; set `DF_LEDGER_DB` to move it.
Each row includes the prior row's hash, and the current hash covers the event ID,
timestamp, category, action, paper/live mode, canonical payload, and prior hash.
SQLite triggers reject ordinary updates and deletes. Run verification regularly:

```bash
./run.sh action ledger-audit -- verify
./run.sh action ledger-audit -- export --output ./ledger-2026-08-25.jsonl
```

This is tamper-evident, not magically tamper-proof: a machine administrator can
replace the database and application together. For stronger assurance, archive
exports or published terminal hashes to storage controlled by a separate account.
Credentials, LLM chat, and bot secrets are deliberately excluded from events.

## Safety model

- Paper trading is the default; live trading requires `ALPACA_LIVE=true` and a
  second typed `LIVE` confirmation.
- Deterministic checks—not the LLM—authorize or block orders and alerts.
- Risk-increasing order submission fails closed if its ledger authorization write
  fails. Cancellation and full-position close stay fail-open so an audit problem
  cannot prevent reducing exposure.
- Research distinguishes embedded source evidence from generated narrative.
- Execution analysis marks missing market matches as unmatched instead of silently
  treating their slippage as zero.

## First-version limitations

- Quotes and account snapshots use REST polling; order fills, partial fills,
  cancellations, and rejections arrive over Alpaca's `trade_updates` stream,
  with REST polling retained for reconciliation.
- Equity stock data exposes the best quote and sizes, not a full depth-of-book. BTC/USD uses Alpaca's crypto order-book endpoint.
- Order replacement, fractional position reduction, extended-hours controls, and opening news links are not yet in the UI.
- OpenInsider filing URLs are retained but cannot yet be opened or selected from
  the TUI, and upstream homepage outages can leave the panel on a stale cache.
- Stock snapshots use the IEX feed for broad account compatibility.
