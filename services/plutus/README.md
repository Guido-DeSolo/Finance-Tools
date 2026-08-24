# Plutus research backend

This directory is the backend/service side of the Finance Tools application.
The Dixie terminal and Finance Shell are the interactive frontend. Keep service
workers, user actions, and shared deterministic logic separate:

```text
Dixie / Finance Shell (frontend)
              |
              +--> plutus actions  -> finite user-requested research
              |
              +--> plutus services -> ingestion and scheduled scoring workers
                                      |
                                      +--> PostgreSQL / Alpaca / OpenInsider
```

Use `./plutus services` and `./plutus actions` to inspect the two catalogs.
`./plutus service NAME` runs a worker in the foreground, making it suitable for
systemd or another supervisor. `./plutus action NAME` runs a finite interactive
or research operation. `./plutus catalog` provides the same boundary as JSON for
future UI viewports.

The supplied `systemd/plutus@.service` template keeps each worker as a distinct
supervised unit. For example, after linking it into the user unit directory,
`systemctl --user start plutus@news-ingest.service` runs only the news worker.
The unit defaults to backtest mode and reads optional local configuration from
`~/.config/plutus/plutus.env`; that private file is never part of this repository.

`PLUTUS_MODE` accepts `backtest`, `shadow`, `paper`, or `live` and defaults to
`backtest`. No imported module currently places orders. Future execution code
must use the runtime guard in `plutus_core/runtime.py` and require a separate
explicit acknowledgement for live mode.

## Preserved research pipeline

This repository builds ranked equity research candidates from deterministic data.
The candidate packet is the immutable interface between the research pipeline and
the model layer; model output must not modify source packets or ranking inputs.

## Pipeline

```text
OpenInsider + Alpaca market/news data
                ↓
          PostgreSQL tables
                ↓
     deterministic feature scoring
                ↓
       immutable candidate packet
                ↓
       structured LLM thesis
                ↓
         debate models (later)
                ↓
       deterministic risk rules
                ↓
           paper execution
```

The current code covers ingestion, schema creation, watchlist scoring, candidate
packet generation, one evidence-only Ollama analyst, and an exploratory
insider-event backtest. It does not place orders.

## Setup

Create a virtual environment, install `requirements.txt`, and put these values in
`.env` at the repository root:

```dotenv
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
DATABASE_URL=postgresql://...
```

Set `BROKER_ENV_PATH` to use a different env file. Process environment variables
override values from the file.

Apply `data/schema.sql` to PostgreSQL, then run scripts from the repository root.
Typical research generation is:

```bash
python data/watchlist.py
python data/candidate_packet.py --limit 30 --validate \
  --output data/candidate_packets.json
```

Run offline tests with:

```bash
python -m unittest discover -s tests -v
```

## Candidate packet contract

The top-level document contains `generated_at`, `candidate_count`,
`score_selection`, and `packets`. Each packet contains:

- `rank` and `symbol`
- `watchlist`: the latest deterministic component scores and source features
- `insider_events`: recent aggregated purchase/sale filing evidence
- `news`: recent article metadata and summaries
- `market`: adjusted daily-bar provenance, quality status, rejection reasons, and
  summary statistics when quality checks pass

`data/candidate_packet.py --validate` enforces required fields, ISO dates, symbol
consistency, unique symbols, market-quality invariants, and finite numeric values.
Packets are evidence inputs; model-generated theses belong in a separate artifact.

## Model boundary

`data/evidence_summary.py` first reduces a validated packet into compact,
normalized facts with percentage returns, stable news IDs, availability flags,
and quality concerns. `agents/analyst.py` sends only that summary to Ollama,
validates its interpretation and evidence references, and inserts it into
`agent_analyses` with the summary, source packet, and raw response:

```bash
python agents/analyst.py --symbol OTLK
```

The defaults are `http://192.168.0.2:11434` and `analyst:latest`. Override them
with `OLLAMA_BASE_URL` and `ANALYST_MODEL`. The model receives no tools or broker
or database credentials; only the local caller persists validated output. Debate,
risk decisions, and execution remain separate stages.
