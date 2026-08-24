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
`news-ingest`, `insider-ingest`, and `watchlist-refresh`. Actions are
`candidate-packets`, `insider-backtest`, and `benchmark-quant-v2`.

There is no backend LLM or sentiment-analysis pipeline. News is collected as
raw information for the terminal feed. The only LLM feature is the separate,
user-controlled Chat tab.

`DF_FINTECHTERM_MODE` accepts `backtest`, `shadow`, `paper`, or `live` and
defaults to `backtest`. Current backend workers do not place orders.

Research scripts use PostgreSQL through `DATABASE_URL`; credentials and
databases remain outside Git. Apply `data/schema.sql` additively. Existing
databases are not dropped or migrated automatically.

Run tests with `python3 -m unittest discover -s tests -v`.
