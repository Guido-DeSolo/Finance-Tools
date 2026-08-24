# Dependency-free technical indicators

An importable Python package implementing common technical-analysis
indicators using only the standard library. It provides aligned output series,
input validation, type hints, descriptive function names, and conventional
uppercase aliases.

Included indicators:

- On-Balance Volume (`obv`, `OBV`)
- Average Directional Index (`average_directional_index`, `ADX`)
- Accumulation/Distribution Line (`accumulation_distribution_line`, `ADL`)
- Aroon (`aroon_indicator`, `AROON`)
- Moving Average Convergence/Divergence (`macd`, `MACD`)
- Relative Strength Index (`rsi`, `RSI`)
- Stochastic oscillator (`stochastic_oscillator`, `STOCHASTIC`)

## Import directly from this repository

Run a script from this directory, or add this directory to `PYTHONPATH`:

```python
import technical_indicators as ta

close = [10, 11, 10, 12]
volume = [100, 150, 120, 200]
print(ta.OBV(close, volume))
```

## Install into another project

From the root of `Finance-Tools`:

```bash
python -m pip install ./packages/technical-indicators
```

Then any Python script can use `import technical_indicators`. Installation
adds no runtime dependencies.

## Test

```bash
cd packages/technical-indicators
python -m unittest discover -s tests -v
```
