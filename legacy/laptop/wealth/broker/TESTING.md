# Indicator validation

No third-party packages are required.

To see exact, unrounded inputs and outputs for a realistic fake market:

```bash
python raw_example.py
```

This prints all 35 synthetic daily candles followed by the raw arrays returned
by every indicator. It also walks through individual OBV and ADL calculations
using the displayed source values.

To inspect calculated values and then run every automated check:

```bash
python validate_indicators.py
```

To run only the automated suite:

```bash
python -m unittest discover -v
```

The suite covers known hand-calculated answers, Wilder's published RSI
worksheet example, warm-up boundaries, flat and trending markets, output
bounds, alignment, named results, public aliases, input immutability,
malformed OHLC bars, bad periods, mismatched lengths, unsafe type coercion,
non-finite data, negative volume, and arithmetic overflow.

The visual report deliberately uses short periods so every transition can be
checked by hand. A dash means that an indicator has not accumulated enough
observations to produce a value.
