# DF-FinTechTerm services and actions

This directory contains non-visual application workers and deterministic
research tools. It deliberately separates services, finite user actions, and
shared deterministic data code.

```bash
./run.sh services
./run.sh service NAME [ARGS]
./run.sh actions
./run.sh action NAME [ARGS]
./run.sh catalog
```

Services include market/news ingestion, retention, watchlist scoring, and
`alert-scan`. Actions include `candidate-packets`, `daily-research`,
`alert-manage`, `insider-backtest`, and `benchmark-quant-v2`.

## Discord and Telegram alerts

Alert rules live beside streamed market data in SQLite. Supported metrics are
`price`, `rsi`, `adx`, `macd`, `macd_signal`, `macd_histogram`, `stochastic_k`,
and `stochastic_d`. Operators are `gt`, `gte`, `lt`, `lte`, `crosses_above`,
and `crosses_below`.

```bash
./run.sh action alert-manage add AAPL price crosses_above 250 \
  --cooldown 3600 --to discord --to telegram
./run.sh action alert-manage add NVDA rsi gte 70 --to telegram
./run.sh action alert-manage list
./run.sh action alert-manage remove 1
./run.sh action alert-manage test --to discord
./run.sh service alert-scan
```

Configure Discord with `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID`; the bot
needs View Channel and Send Messages permissions. Configure Telegram with
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Messages use plain text, Discord
mentions are disabled, and tokens are never stored in SQLite.

Copy `systemd/df-fintechterm.env.example` to
`~/.config/df-fintechterm/df-fintechterm.env`, fill only the desired transport,
and restrict it to the owning user. The optional
`df-fintechterm-alert-scan.timer` evaluates rules once per minute. Failed
deliveries remain queued for up to ten attempts; condition state and cooldowns
prevent repeated messages while a threshold remains continuously true.

`news-retention` deletes articles older than seven days from the live SQLite
feed and, when `DATABASE_URL` is configured, the PostgreSQL news archive. Run it
once with `./run.sh service news-retention`; the supplied
`systemd/df-fintechterm-news-retention.timer` runs it hourly. Override the
window only when needed with `--days N`.

`daily-research` is an explicit user action that sends a bounded copy of each
validated candidate packet—including up to five tagged news items—to the fixed
local Ollama model. It writes a Markdown brief, complete evidence JSON, and an
auditable Jupyter notebook under `DF_RESEARCH_OUTPUT_DIR` (default:
`~/.local/share/df-fintechterm/research`). The model narrative is never used as
a score or order input. There is no autonomous sentiment or execution pipeline.

`DF_FINTECHTERM_MODE` accepts `backtest`, `shadow`, `paper`, or `live` and
defaults to `backtest`. Current backend workers do not place orders.

Research scripts use PostgreSQL through `DATABASE_URL`; credentials and
databases remain outside Git. Apply `data/schema.sql` additively. Existing
databases are not dropped or migrated automatically.

Run tests with `python3 -m unittest discover -s tests -v`.
