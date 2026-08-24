# Dixie Flatline Alpaca Terminal

A first-version, keyboard-driven account and order terminal for Alpaca. It shows account equity and liquidity, positions, recent orders, watched quotes, BTC/USD order-book prices, and a scrollable NewsData.io feed.

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
```

## Keys

- `b` / `s`: place a buy/sell order
- `c`: cancel the newest open order (`latest`) or an order whose ID prefix is known
- `x`: close an entire position
- `w`: add/remove a ticker symbol
- Up/Down or `j`/`k`: scroll news
- `q` or Escape: quit

The order form supports market, limit, stop, and stop-limit orders, using quantity or `$`-prefixed notional amounts. Alpaca validates combinations and returns rejection details in the status line.

## First-version limitations

- It uses REST polling rather than streaming sockets.
- Equity stock data exposes the best quote and sizes, not a full depth-of-book. BTC/USD uses Alpaca's crypto order-book endpoint.
- Order replacement, fractional position reduction, extended-hours controls, persistent watchlists, and opening news links are not yet in the UI.
- Stock snapshots use the IEX feed for broad account compatibility.
