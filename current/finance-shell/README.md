# Finance Shell

Finance Shell is the command center for the market-data and finance tools on
this computer. It can download historical bars, collect live trades and order
books, collect real-time news, analyze news sentiment with a local Ollama model,
classify stocks by industry, open Tickrs, run technical-indicator tests, and
perform basic financial calculations.

These tools do not place orders. They are informational, not financial advice.

## Start here

Run commands directly from the project:

```bash
cd /home/guyyatsu/Documents/finance-shell
./fsh help
```

Or make `fsh` available in the current terminal from any directory:

```bash
source /home/guyyatsu/Documents/finance-shell/activate.bash
fsh help
```

Check that the local tools and database are healthy:

```bash
fsh doctor
fsh alpaca status
```

The main database is:

```text
/home/guyyatsu/Documents/finance-shell/data/alpaca.sqlite3
```

## Alpaca credentials

Finance Shell automatically loads persistent Alpaca credentials from:

```text
/home/guyyatsu/.config/finance-shell/alpaca.env
```

The file should contain:

```bash
APCA_API_KEY_ID="your-key-id"
APCA_API_SECRET_KEY="your-secret-key"
```

Protect it:

```bash
chmod 600 /home/guyyatsu/.config/finance-shell/alpaca.env
```

You can alternatively export the variables in the current terminal. Starting
the stream daemon with exported credentials creates or updates the persistent
file automatically.

Never put credentials in the SQLite database or commit the environment file to
source control.

## Historical market data

Download daily stock bars:

```bash
fsh alpaca history AAPL --class stock --timeframe 1Day --start 2020-01-01
```

Download every available one-minute stock bar:

```bash
fsh alpaca history AAPL \
    --class stock \
    --timeframe 1Min \
    --start 1970-01-01 \
    --feed iex
```

Download crypto bars:

```bash
fsh alpaca history BTC/USD \
    --class crypto \
    --timeframe 1Hour \
    --start 2024-01-01 \
    --location us
```

Finance Shell follows all Alpaca pagination automatically. Repeating a request
is safe because existing bars are updated rather than duplicated.

Useful options:

- `--timeframe 1Min`, `1Hour`, `1Day`, and other supported windows
- `--start DATE` and `--end DATE`
- `--feed iex|sip|boats|otc` for stocks; the default is `iex`
- `--location us|us-1|eu-1` for crypto
- `--max-pages N` for a small test; capped runs are marked `partial`
- `fsh alpaca timeframes` to list accepted timeframe formats

### Download a file of stock symbols

Create a text file with one symbol per line:

```text
AAPL
MSFT
NVDA
# Comments and blank lines are allowed
```

Then run:

```bash
fsh alpaca history-list symbols.txt
```

This requests complete one-minute IEX history for each symbol. A symbol is
skipped when any stock bars for it already exist. This includes partially
downloaded symbols; use the single-symbol history command if you need to finish
or repeat one of those downloads. Failures are reported, but the remaining
symbols are still attempted.

### Asset catalog

Download Alpaca's stock and crypto asset catalogs:

```bash
fsh alpaca sync-assets
```

This catalog describes available assets. It is separate from price history.

## Live market-data daemon

The live collector is one persistent systemd user service. Its watchlist is
stored in SQLite.

Add stocks:

```bash
fsh alpaca stream add AAPL --class stock --feed iex
fsh alpaca stream add MSFT --class stock --feed iex
```

Add crypto:

```bash
fsh alpaca stream add BTC/USD --class crypto --location us
```

View or remove watchlist entries:

```bash
fsh alpaca stream list
fsh alpaca stream remove AAPL --class stock
fsh alpaca stream remove BTC/USD --class crypto
```

Control the daemon:

```bash
fsh alpaca stream start
fsh alpaca stream status
fsh alpaca stream restart
fsh alpaca stream stop
```

Adding or removing a symbol automatically restarts the daemon when it is
already running. It does not start a stopped daemon. Once enabled, the service
starts with the systemd user session.

View service errors:

```bash
journalctl --user -u fsh-alpaca-stream.service -n 100 --no-pager
journalctl --user -u fsh-alpaca-stream.service -f
```

The collector stores:

- Every raw trade, stock quote, and crypto book update in `live_market_events`
- Deduplicated trades in `live_trades`
- The current reconstructed book in `live_orderbooks`
- Real-time Alpaca articles in `news_articles`, linked through `news_article_symbols`
- The desired symbols in `stream_watchlist`

Crypto provides full-depth books. Stocks provide trades and top-of-book quotes.
The daemon never submits orders.

The same daemon subscribes to Alpaca's real-time news feed for every watchlist
symbol. View the newest stored articles globally or for one symbol:

```bash
fsh alpaca news
fsh alpaca news AAPL
fsh alpaca news BTC/USD --limit 20
```

## Local Ollama news sentiment

Sentiment analysis reads stored Alpaca articles, sends them to Ollama's local
HTTP API, validates a structured response, and stores the result in
`news_sentiment`. It never sends articles to a remote LLM unless you explicitly
change `--host` to a remote address.

Install Ollama, start it, and download a model before first use:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
```

The default model is `llama3.2:3b`; override it with `--model` or
`OLLAMA_MODEL`:

```bash
ollama pull llama3.2:3b
```

Find article IDs:

```bash
fsh alpaca news --limit 20
```

Analyze one article:

```bash
fsh sentiment analyze ARTICLE_ID
fsh sentiment analyze ARTICLE_ID --model llama3.2:3b
```

Analyze the oldest articles that do not yet have a result for the selected
model and prompt version:

```bash
fsh sentiment pending --limit 10
```

View results globally or for one symbol:

```bash
fsh sentiment list
fsh sentiment list AAPL --limit 20
```

Each result includes a five-level label, numeric score from -1 to 1,
confidence from 0 to 1, impact horizon, short rationale, model, prompt version,
runtime metadata, and the raw Ollama response. Running the same article/model
again refreshes that result; different models remain separate.

## Live terminal viewer

Show an overview of all current books:

```bash
fsh alpaca stream view
```

Show one detailed book and recent trades:

```bash
fsh alpaca stream view BTC/USD
fsh alpaca stream view AAPL --class stock
```

Viewer options:

```bash
fsh alpaca stream view BTC/USD --depth 20 --interval 0.5
fsh alpaca stream view BTC/USD --once
```

Press Ctrl-C to exit. The viewer opens SQLite read-only and does not interrupt
the collector.

## Industry classification

Industry tags come from the SEC Standard Industrial Classification system. SEC
automated requests must identify a person and contact address:

```bash
export SEC_USER_AGENT="Your Name your-email@example.com"
```

Classify every stock that contains stored market data:

```bash
fsh classify refresh
```

Refresh selected stocks only:

```bash
fsh classify refresh AAPL MSFT NVDA
```

View the stored classifications:

```bash
fsh classify list
```

Results are stored in `symbol_classifications`. Each record includes the SEC
CIK, SIC code, detailed industry, broad sector, company name, source, status,
and refresh time. Securities without an applicable SIC value are marked
unmatched or unclassified rather than being assigned a guessed industry.

## Tickrs launchers

Open Tickrs with every unique symbol that has historical or live data:

```bash
fsh tickrs
```

Preview the generated command:

```bash
fsh tickrs --dry-run
```

Forward options to Tickrs after `--`:

```bash
fsh tickrs -- --summary --time-frame 1W
```

Choose a stored industry from an interactive menu, then open all of its
database-backed symbols:

```bash
fsh tickrs-industry
```

Select an industry without the menu or preview the result:

```bash
fsh tickrs-industry --industry "Prepackaged Software"
fsh tickrs-industry --industry "Prepackaged Software" --dry-run
```

Run `fsh classify refresh` before using the industry launcher. Tickrs launchers
only include symbols that actually contain market data; watchlist-only and
catalog-only symbols are ignored.

## Ticker launcher

Open the installed `ticker` terminal application with every unique symbol that
has historical or live data:

```bash
fsh ticker
```

The symbol list is regenerated from SQLite every time. Preview the generated
command or pass native ticker options after `--`:

```bash
fsh ticker --dry-run
fsh ticker -- --show-fundamentals --sort alpha --interval 2
```

Like the Tickrs launcher, this ignores catalog-only and watchlist-only symbols.
Crypto pairs are converted from database form such as `BTC/USD` to Ticker's
Yahoo-style `BTC-USD` form.

## Technical indicators

Run the technical-analysis test suite:

```bash
fsh indicators test
```

Show the validation report or deterministic example data:

```bash
fsh indicators report
fsh indicators example
```

The indicator library includes ADL, ADX, Aroon, MACD, OBV, RSI, and stochastic
oscillator calculations.

## Calculators

Compound growth with an optional monthly contribution:

```bash
fsh calc compound 1000 7 10 100
```

Gain or loss:

```bash
fsh calc gain 1250 1430
```

Budget remainder and savings rate:

```bash
fsh calc budget 3200 1200 450 200
```

Allocate a total by weights:

```bash
fsh calc allocate 1000 60 30 10
```

Calculations use Python decimal arithmetic. Compound contributions are treated
as end-of-month payments with monthly compounding.

## Simple price lookups

```bash
fsh price bitcoin
fsh price silver
```

Bitcoin uses CoinGecko. Silver requires `METALPRICE_API_KEY` in the environment.
These commands print results and do not store them in the database.

## Database inspection

Show high-level row counts:

```bash
fsh alpaca status
```

Open the database manually:

```bash
sqlite3 /home/guyyatsu/Documents/finance-shell/data/alpaca.sqlite3
```

Useful SQLite commands:

```sql
.tables
.schema bars
SELECT asset_class, symbol, count(*) FROM bars GROUP BY asset_class, symbol;
SELECT event_type, count(*) FROM live_market_events GROUP BY event_type;
SELECT updated_at, headline FROM news_articles ORDER BY updated_at DESC LIMIT 10;
SELECT article_id, label, score, confidence FROM news_sentiment ORDER BY analyzed_at DESC;
SELECT symbol, industry, sector FROM symbol_classifications ORDER BY symbol;
.quit
```

The database uses WAL mode, so `alpaca.sqlite3-wal` and
`alpaca.sqlite3-shm` may exist while tools are running. Include the database and
its sidecars when copying a live database, or stop the daemon and checkpoint it
first.

## Troubleshooting

Start with:

```bash
fsh doctor
fsh alpaca stream status
journalctl --user -u fsh-alpaca-stream.service -n 100 --no-pager
```

Common checks:

- Confirm `alpaca.env` exists, contains both Alpaca variables, and has mode 600.
- Confirm at least one symbol appears in `fsh alpaca stream list` before start.
- Use IEX if the Alpaca account does not include SIP access.
- Run `fsh classify refresh` before `fsh tickrs-industry`.
- Confirm `curl http://127.0.0.1:11434/api/tags` works before sentiment analysis.
- Run `ollama pull llama3.2:3b` if the default sentiment model is unavailable.
- Use `--max-pages 1` for a small historical-download test.
- Use `fsh alpaca stream view --once` for a non-interactive stream snapshot.

For command-specific options, add `--help`, for example:

```bash
fsh alpaca history --help
fsh alpaca stream view --help
fsh classify --help
fsh sentiment --help
fsh tickrs-industry --help
```
