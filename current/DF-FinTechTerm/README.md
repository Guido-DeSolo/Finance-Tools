# DF-FinTechTerm

A keyboard-driven account, order, and finance-tools terminal for Alpaca. It
shows account equity and liquidity, positions, recent orders, watched quotes,
BTC/USD order-book prices, and a scrollable NewsData.io feed. Its Finance Shell
palette also exposes every tool provided by `fsh`. The right pane switches
between the news reel and a conversational local LLM log.

## Start

Python 3 and `requests` are required. Export credentials (do not commit them):

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
export ALPACA_WATCHLIST='SPY,AAPL,NVDA,MSFT'
export ALPACA_REFRESH_SECONDS=3
```

Finance Shell is embedded in this application. Use it from the TUI with `f`
or invoke the same dispatcher directly:

```bash
./run.sh fsh help
./run.sh fsh alpaca status
./run.sh fsh calc gain 1250 1430
./run.sh services
./run.sh actions
```

`services` lists ingestion and scoring workers intended for supervision or
scheduling. `actions` lists finite operations initiated by a user. Run a named
entry with `./run.sh service NAME` or `./run.sh action NAME`.

## Keys

- `a`: switch between the account dashboard and live technical-analysis view
- `Tab`: switch the right pane between News and Local Chat
- `Enter`: send a prompt while the Local Chat tab is active
- `b` / `s`: place a buy/sell order
- `f`: open the complete Finance Shell tool palette
- `c`: cancel the newest open order (`latest`) or an order whose ID prefix is known
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
- News sentiment analysis, pending processing, and reports
- Alpaca asset sync, historical data, batch history, status, stored news, and
  timeframe help
- Per-trade rolling technical analysis for live-order-book symbols
- Stream watchlist management, daemon controls, status, and live view
- Compound-growth, gain/loss, budget, and allocation calculators
- Finance Shell doctor and help

Tools that need parameters show the expected arguments before prompting. The
TUI constructs an argument vector directly and never invokes a command shell.
Terminal-native tools temporarily take over the display; press Enter after
they finish to return to the dashboard.

Press `a` for a full-screen view of watched symbols whose order books received
a trade in the last five minutes. Symbols are sorted by their most recent
analysis update. Each entry shows buffer depth plus RSI, ADX, MACD, signal,
histogram, OBV, ADL, Aroon up/down, and stochastic K/D values.

The order form supports market, limit, stop, and stop-limit orders, using quantity or `$`-prefixed notional amounts. Alpaca validates combinations and returns rejection details in the status line.

## First-version limitations

- It uses REST polling rather than streaming sockets.
- Equity stock data exposes the best quote and sizes, not a full depth-of-book. BTC/USD uses Alpaca's crypto order-book endpoint.
- Order replacement, fractional position reduction, extended-hours controls, persistent watchlists, and opening news links are not yet in the UI.
- Stock snapshots use the IEX feed for broad account compatibility.
