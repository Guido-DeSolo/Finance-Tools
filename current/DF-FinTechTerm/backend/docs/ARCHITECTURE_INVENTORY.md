# DF-FinTechTerm architecture inventory and gap report

Date: 2026-08-24

## Scope and safety

The expected `/opt/broker` tree is mounted here as
`/home/guyyatsu/mount/broker`. This inventory was performed without changing
ingestion code, applying the database schema, contacting Alpaca, placing an
order, or reading secret values. The mounted tree does not contain Git metadata.

The repository-level `.env` exists with mode `0600` and is not readable by the
current user. Configuration code expects `ALPACA_API_KEY`,
`ALPACA_SECRET_KEY`, and `DATABASE_URL`, with process environment values taking
precedence over the file. Database contents and remote row counts therefore
remain unverified in this pass.

The offline baseline is healthy: all 57 unit tests pass with the system Python.
The mounted virtual environment exists, but its interpreter cannot be executed
from this mount (`Operation not permitted`), consistent with a no-exec mount.

## Current architecture

### Data ingestion and storage

PostgreSQL is the intended persistent store. `data/schema.sql` defines:

- one-minute `bars`, keyed by `(symbol, timestamp)`;
- separate IEX and SIP daily-bar tables;
- Alpaca news articles;
- normalized insider transactions plus deterministic aggregation views;
- timestamped watchlist scores; and
- persisted, structured analyst outputs with the input packet and raw response.

Existing ingestion paths are:

- `data/ingest.py`: paginated Alpaca IEX one-minute bars, currently configured
  for SPY from 2024 onward;
- `data/daily_ingest.py`: batched IEX daily bars for the insider-derived symbol
  universe;
- `data/daily_ingest_sip.py`: near-duplicate SIP daily ingestion;
- `data/news_ingest.py`: paginated Alpaca news ingestion;
- `data/insider.py`: OpenInsider-style Form 4 scraping and normalization.

The checked-out tree contains only small JSON packets and frozen evaluation
corpora. The large historical archive appears to live in external PostgreSQL;
its size, coverage, timestamp bounds, and approximately 6,181-symbol universe
cannot be confirmed without database access.

### Deterministic research pipeline

The strongest existing boundary is:

```text
PostgreSQL observations
  -> deterministic watchlist score
  -> validated immutable candidate packet
  -> compact evidence summaries
  -> constrained specialist interpretation
```

`data/candidate_packet.py` performs market quality checks and derives daily
returns, volatility, volume ratios, and rolling-high/low distance. Packet
validation rejects duplicate symbols, non-finite numbers, malformed dates,
invalid OHLC, and inconsistent unavailable-market states.

`data/market_summary.py` and `data/quant_signal.py` provide a deterministic
market reducer and categorical technical signal with explicit abstention when
core evidence is unavailable. `docs/decisions/0001-deterministic-quant.md`
records the decision to prefer this over an unsuccessful model-based QUANT
benchmark.

This is useful research functionality, but it is based on daily summary fields;
it is not yet the requested reusable, multi-horizon `bars -> features` engine.

### News v1 and v2

NEWS v2 closely matches the DF-FinTechTerm specification:

- `data/news_summary.py` filters by an as-of boundary, orders deterministically,
  removes near duplicates, assigns stable local IDs, and represents no news as
  an empty article set;
- `agents/news_v2.py` asks the model only for sentiment and materiality for each
  supplied article;
- `data/news_signal.py` deterministically owns aggregation, confidence,
  conflicts, counts, balance, maximum materiality, and no-news abstention;
- `evaluation/news_v2_freeze.json` freezes the classifier, aggregator, corpus,
  and benchmark hashes.

NEWS v1 (`agents/news.py`) still exists and gives the model broader catalyst and
risk responsibilities. It should be retained as a historical benchmark, but
NEWS v2 should be the only forward architecture unless a versioned experiment
explicitly says otherwise.

### Other specialists and synthesis

- Insider signals are deterministically reduced from normalized Form 4 data.
- A deterministic QUANT signal exists alongside the older model QUANT agent.
- `data/synthesis_input.py` whitelists compact specialist outputs.
- `agents/synthesis.py` uses a constrained schema and prevents references to
  abstaining branches, but still asks a model to emit directional action and
  confidence. That output must remain research interpretation; it is not a
  portfolio decision and must never be wired directly to execution.
- The older general analyst persists grounded prose and provenance, but its
  schema is not the future decision ledger.

### Benchmarks and tests

Frozen manifests exist for analyst v1, NEWS v1, NEWS v2, QUANT model v1,
deterministic QUANT v2, and synthesis v1. Their hash-lock tests pass. This is a
good benchmark-freeze mechanism and should be preserved.

The 57 tests cover packet validation, evidence reduction, deterministic scoring,
abstention, constrained model outputs, and frozen artifacts. They do not yet
cover fee arithmetic, position sizing, P&L, bar aggregation, risk enforcement,
execution simulation, replay boundaries, outcome scoring, or look-ahead
prevention because those components do not exist yet.

### Alpaca and execution safety

Alpaca market-data ingestion and an account-authentication smoke script exist.
The smoke script calls `https://api.alpaca.markets/v2/account`, which is the live
trading host, although it only reads account state. There is no centralized
execution-mode contract, no `DF_FINTECHTERM_MODE`, and no paper/live guard.

The current README explicitly says the project does not place orders. The
`backtest/`, `risk/`, and `trading/` directories are empty, so importing current
modules cannot submit a trade. This safe state should be maintained while the
deterministic foundation is built.

## Gap analysis

| Area | Current state | Required next state | Priority |
|---|---|---|---|
| Execution mode | No centralized mode; account smoke test uses live host | Typed `backtest/shadow/paper/live` mode, default `backtest`, explicit live opt-in | Critical before any order code |
| Bar contract | Minute and daily schemas differ; minute key omits source/timeframe | Canonical UTC bar type with source, asset class, feed, timeframe, and provenance | 1 |
| Raw preservation | Bar upserts overwrite prior broker values | Append-only raw observations plus separately regenerated normalized/derived data | 1 |
| Feature engine | Small daily summary and deterministic categorical signal | Pure multi-horizon feature functions with definitions and fixture tests | 2 |
| Aggregation | Higher timeframes downloaded/stored separately | Deterministic 1m-to-5m/15m/1h/4h/1d aggregation with boundary tests | 2 |
| Microstructure | No quote/order-book schema or features | Compact spread, midpoint, depth, imbalance, liquidity, and trade-direction features | 3 |
| Decisions | Model research actions only | Immutable typed BUY/SELL/HOLD/CASH decision object with reason codes and provenance | 4 |
| Position sizing | Missing | Deterministic target-allocation sizing with cash, exposure, volatility, liquidity, and minimum-order constraints | 4 |
| Fees | Missing | Pluggable fee protocol and zero-fee placeholder; broker algorithm added later as a version | 5 |
| Slippage/fills | Missing | Pluggable execution model separating order from one or more fills | 5 |
| Risk | Flags exist, enforcement does not | Independent deterministic proposal accept/reduce/reject engine | 6 |
| Replay | Only exploratory insider-event backtest | Clocked historical replay exposing only observations at or before decision time | 7 |
| Evaluation | Specialist correctness benchmarks only | Horizon outcomes, MFE/MAE, gross/net returns, counterfactuals, and immutable scoring | 8 |
| Portfolio accounting | Missing | USD ledger plus asset quantities/equivalents, with fees and fills reconciled | 8 |
| Baselines | No portfolio baselines | Cash and buy-and-hold first; DCA/SMA/random later | 9 |
| Live/shadow | Missing | Same contracts as replay, initially emitting shadow decisions only | 10 |

## Data-model concerns to resolve without destructive migration

The existing tables should remain in place until their live PostgreSQL contents
are measured. New versioned tables or additive migrations are safer than changing
primary keys in place.

In particular:

1. `bars` has no `source`, `feed`, `timeframe`, `asset_class`, ingestion time, or
   raw payload identity. Its `(symbol, timestamp)` key cannot distinguish two
   providers or feeds.
2. `bars`, `daily_bars`, `daily_bars_sip`, and news ingestion use conflict updates.
   That is useful for a current normalized view but is not immutable raw evidence.
3. `daily_bars` uses `DATE`, while minute bars use `TIMESTAMPTZ`. The canonical
   contract needs an aware UTC interval start and explicit timeframe.
4. Derived watchlist scores and agent analyses have partial provenance, but there
   is no shared registry for feature, strategy, prompt, model, fee, and execution
   versions.
5. Signal, decision, order, fill, fee, portfolio snapshot, and evaluation are not
   yet represented as separate entities.

## Duplicate or legacy candidates

These are candidates for labeling, not deletion:

- NEWS v1 versus NEWS v2: preserve v1 benchmark artifacts; route new work to v2.
- Model QUANT versus deterministic QUANT v2: preserve the failed/frozen model
  benchmark; route strategy inputs to deterministic output.
- `daily_ingest.py` versus `daily_ingest_sip.py`: extract shared pagination and
  persistence only after regression tests cover both feed variants.
- `test_alpaca.py` and `data/news_test.py`: ad-hoc network smoke scripts execute at
  import time and should eventually become explicit CLI diagnostics.
- Empty `backtest/`, `risk/`, `trading/`, and `debate/` directories represent
  intentions, not implemented capability.

## Recommended first implementation slice

The first code slice should be deliberately small and independent of Alpaca and
PostgreSQL:

1. Introduce a `df-fintechterm` package containing typed, timezone-aware contracts for
   `Bar`, `FeatureSnapshot`, `SpecialistSignal`, and `Decision`.
2. Make `DecisionAction` explicitly distinguish `BUY`, `SELL`, `HOLD`, and `CASH`.
3. Add an `ExecutionMode` parser whose absent value is `backtest` and whose live
   value requires a second explicit acknowledgement at the eventual executable
   boundary.
4. Define `FeeModel` and `SlippageModel` protocols with version identifiers, plus
   deterministic zero-fee and zero-slippage implementations for tests only.
5. Add exhaustive contract tests for finite numeric values, UTC-aware timestamps,
   allocation bounds, immutable values, and safe mode defaults.

This establishes stable seams without touching working ingestion or pretending
that a simulator already exists. The next slice can normalize existing database
rows into the canonical `Bar` contract and implement deterministic aggregation.

## Verification required before database work

With read-only database credentials or an operator-provided inventory export,
collect:

- PostgreSQL version and schema search path;
- row counts and byte sizes for every table;
- distinct symbols, sources/feeds, earliest/latest timestamps, and null rates;
- timezone and duplicate checks for bars and news;
- actual one-minute coverage and missing-interval statistics;
- counts of candidate packets, analyses, and insider/news records;
- existing grants, backup/restore process, and migration mechanism.

No bulk ingestion, schema rewrite, or live execution should begin before that
inventory is recorded.
