# DF-FinTechTerm

A keyboard-driven account, order, and finance-tools terminal for Alpaca. It
shows account equity and liquidity, positions, recent orders, watched quotes,
BTC/USD order-book prices, and a scrollable NewsData.io feed. Its Finance Shell
palette also exposes every tool provided by `fsh`. The right pane switches
between the news reel and a conversational local LLM log. Shift-Tab cycles the
main area between the account dashboard, stored-industry ticker view, and live
technical-analysis view; ordinary Tab remains dedicated to News/Chat.
The right-side panel remains visible beside all four main views. Shift-Tab
cycles Dashboard, Ticker, Industry, and Live TA. The Ticker tab shows live
quotes for the personal watchlist persisted in the stream daemon database. In
the Industry tab, choose an industry with the arrow keys and press `t` to
open the actual `tickrs` chart/summary interface for exactly those constituents;
exiting `tickrs` restores the same selected Industry tab.
Use Finance Tools → `Classification · populate all Alpaca industries` to sync
and classify Alpaca's complete active U.S. equity catalog for this view.

A separate full-width Trade Ticket remains fixed along the bottom beneath both
panels. It shows paper/live mode, the symbols currently eligible to sell, and
the order-management controls. Buys accept any Alpaca-supported symbol. Sells
are blocked locally unless the account currently reports a positive holding in
the requested symbol; zero and short positions are not sell-eligible.

## Start

Python 3 and `requests` are required. The embedded industry chart interface also
requires `tickrs` on `PATH`. Export credentials (do not commit them):

```bash
cd /home/guyyatsu/Finance-Tools/current/DF-FinTechTerm
export APCA_API_KEY_ID='...'
export APCA_API_SECRET_KEY='...'
export NEWSDATA_API_KEY='...'
./run.sh
```

Paper trading is the default. To deliberately use real money, also set `ALPACA_LIVE=true`. Live mode is displayed in red and requires typing both `YES` and `LIVE` before a trading action.

Optional setting:

```bash
export ALPACA_REFRESH_SECONDS=3
export DF_RISK_WARN_POSITION_PCT=20
# Optional hard limits; zero disables each limit.
export DF_RISK_MAX_POSITION_PCT=0
export DF_RISK_MAX_ORDER_NOTIONAL=0
export DF_RISK_MAX_DAILY_LOSS=0
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

A persistent daily systemd timer advances every stored Alpaca bar series through
the current API-safe edge, defined as UTC now minus 15 minutes.

## Keys

- `:`: open the command bar (`AAPL`, `AAPL GO`, `DASH`, `ORDERS`, `WATCH`,
  `TICKER`, `INDUSTRY`, or `TA`)
- `a`: switch between the account dashboard and live technical-analysis view
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
- `w`: add/remove a ticker symbol
- Up/Down or `j`/`k`: scroll news, chat, or live analysis
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

## First-version limitations

- Quotes and account snapshots use REST polling; order fills, partial fills,
  cancellations, and rejections arrive over Alpaca's `trade_updates` stream,
  with REST polling retained for reconciliation.
- Equity stock data exposes the best quote and sizes, not a full depth-of-book. BTC/USD uses Alpaca's crypto order-book endpoint.
- Order replacement, fractional position reduction, extended-hours controls, and opening news links are not yet in the UI.
- Stock snapshots use the IEX feed for broad account compatibility.
