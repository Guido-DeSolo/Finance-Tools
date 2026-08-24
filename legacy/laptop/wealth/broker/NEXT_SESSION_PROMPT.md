# Technical-analysis and Alpaca integration handoff

We are working locally in:

```text
/home/guyyatsu/Documents/wealth/broker
```

Please inspect the local project and continue from its current state. Do not
rebuild completed work from scratch.

## What has been built

The local `technical_analysis` package is a dependency-free Python library
implementing:

- On-Balance Volume (`obv` / `OBV`)
- Average Directional Index (`average_directional_index` / `ADX`)
- Accumulation/Distribution Line (`accumulation_distribution_line` / `ADL`)
- Aroon Up and Down (`aroon_indicator` / `AROON`)
- MACD line, signal, and histogram (`macd` / `MACD`)
- Wilder RSI (`rsi` / `RSI`)
- Fast stochastic %K and %D (`stochastic_oscillator` / `STOCHASTIC`)

The production implementation is in:

```text
technical_analysis/__init__.py
```

It has already been hardened to:

- Reject booleans, numeric strings, non-numeric values, NaN, and infinity.
- Enforce equal-length input series.
- Enforce non-negative volume.
- Enforce valid bars (`low <= close <= high`).
- Reject invalid periods and invalid MACD period relationships.
- Use `math.fsum` where more stable aggregation is valuable.
- Detect numerical overflow rather than returning NaN or infinity.
- Preserve input arrays and return newly allocated, index-aligned lists.
- Use `None` for indicator warm-up positions.
- Keep bounded indicators within 0 through 100.

Do not casually change existing warm-up positions, EMA seeding, Wilder
smoothing, zero-range behavior, or public return types. If compatibility
requires a change, first identify and explain the exact contract conflict.

## Existing validation

The dependency-free automated suite is in:

```text
tests/test_indicators.py
```

Run it with:

```bash
python -m unittest discover -v
```

At handoff it contains 31 passing tests, including hand-calculated cases, a
classic Wilder RSI reference value, validation errors, overflow handling,
warm-up boundaries, output invariants, aliases, and result unpacking.

The human-readable validation table is:

```bash
python validate_indicators.py
```

The exact unrounded realistic synthetic example is:

```bash
python raw_example.py
```

`raw_example.py` prints all source OHLCV arrays and raw results from every
indicator, including individual OBV and ADL calculations that can be audited
by hand.

## Next objective

There is a separate research system mounted at:

```text
external/
```

It uses Alpaca Markets historical data. Read the existing historical-data API
client and refit the local technical-analysis system to be compatible with the
data structures and conventions already used there. Prefer a clean adapter or
integration boundary over duplicating calculations. Preserve existing APIs
when practical, and add/update validation for any new public behavior.

Likely relevant source modules include:

```text
external/data/daily_ingest.py
external/data/daily_ingest_sip.py
external/data/ingest.py
external/data/quant_signal.py
external/data/candidate_packet.py
external/tests/test_candidate_packet.py
external/tests/test_quant_signal.py
external/tests/test_market_summary.py
```

First locate the actual Alpaca historical-bars request, response parsing, bar
schema, adjustments, feed, timeframe, pagination, ordering, and missing-data
behavior. Then inspect how market statistics flow into candidate packets and
quant summaries. Base the integration on source evidence, not assumptions
about Alpaca's API.

## Absolute data-safety restrictions

The user explicitly forbids reading the environment file or database. Treat
this as a hard boundary.

Do not open, print, search, parse, copy, hash, inspect, or otherwise read:

```text
.env
.env.*
any database contents
*.db
*.sqlite
*.sqlite3
database dumps
database connection values
stored credentials or secrets
```

Also avoid reading SQL schemas and stored datasets unless the user separately
authorizes it. Reading Python source that describes interfaces is allowed, but
do not execute ingestion scripts or anything that connects to Alpaca or the
database without explicit need and authorization.

When searching `external`, use narrow source-only commands with explicit
exclusions. Never recursively print the entire tree's contents.

## SSHFS warning

`external` is a remote SSHFS mount without root access. During the previous
session it became stale: even harmless reads blocked indefinitely. Use a short,
read-only probe before doing substantive work:

```bash
timeout 5s head -n 5 external/README.md
```

If the probe hangs or times out, stop. Do not launch repeated or parallel reads
against the stale mount. Tell the user the mount must be reconnected. Do not
infer and implement the external contract without reading the relevant source.

## Working style for the next session

1. Confirm the SSHFS source tree responds promptly.
2. State the protected-file exclusions before inspecting it.
3. Read only the relevant Python source and tests.
4. Summarize the observed Alpaca/bar contract before editing.
5. Implement the smallest coherent compatibility layer.
6. Run the local suite plus relevant external offline tests that do not access
   credentials, networks, or databases.
7. Report exactly what changed, what was verified, and any remaining contract
   uncertainty.

