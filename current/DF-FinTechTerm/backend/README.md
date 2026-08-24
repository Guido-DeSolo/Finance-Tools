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

Services are `market-minute`, `market-daily-iex`, `market-daily-sip`,
`news-ingest`, `news-retention`, `insider-ingest`, and `watchlist-refresh`. Actions are
`candidate-packets`, `daily-research`, `insider-backtest`, and `benchmark-quant-v2`.

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
