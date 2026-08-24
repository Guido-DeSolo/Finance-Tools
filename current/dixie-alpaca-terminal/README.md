# Dixie Flatline Alpaca Terminal

A keyboard-driven account, order, and finance-tools terminal for Alpaca. It
shows account equity and liquidity, positions, recent orders, watched quotes,
BTC/USD order-book prices, and a scrollable NewsData.io feed. Its Finance Shell
palette also exposes every tool provided by `fsh`.

## Start

Python 3 and `requests` are required. Export credentials (do not commit them):

```bash
cd /home/guyyatsu/dixie-alpaca-terminal
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
# Optional override; auto-detected in the Finance-Tools repository.
export FINANCE_SHELL='/path/to/finance-shell/fsh'
```

## Keys

- `b` / `s`: place a buy/sell order
- `f`: open the complete Finance Shell tool palette
- `c`: cancel the newest open order (`latest`) or an order whose ID prefix is known
- `x`: close an entire position
- `w`: add/remove a ticker symbol
- Up/Down or `j`/`k`: scroll news
- `q` or Escape: quit

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
- Stream watchlist management, daemon controls, status, and live view
- Compound-growth, gain/loss, budget, and allocation calculators
- Finance Shell doctor and help

Tools that need parameters show the expected arguments before prompting. The
TUI constructs an argument vector directly and never invokes a command shell.
Terminal-native tools temporarily take over the display; press Enter after
they finish to return to the dashboard.

The order form supports market, limit, stop, and stop-limit orders, using quantity or `$`-prefixed notional amounts. Alpaca validates combinations and returns rejection details in the status line.

## First-version limitations

- It uses REST polling rather than streaming sockets.
- Equity stock data exposes the best quote and sizes, not a full depth-of-book. BTC/USD uses Alpaca's crypto order-book endpoint.
- Order replacement, fractional position reduction, extended-hours controls, persistent watchlists, and opening news links are not yet in the UI.
- Stock snapshots use the IEX feed for broad account compatibility.
