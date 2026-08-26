"""Print an inspectable technical-indicator validation report.

Run with ``python validate_indicators.py`` from the repository root.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import technical_indicators as ta


def format_value(value: float | None) -> str:
    return "   —   " if value is None else f"{value:7.2f}"


def print_table(close, high, low, volume) -> None:
    adx = ta.ADX(high, low, close, period=3)
    adl = ta.ADL(high, low, close, volume)
    aroon_up, aroon_down = ta.AROON(high, low, period=3)
    macd, signal, histogram = ta.MACD(close, 2, 4, 2)
    rsi = ta.RSI(close, period=3)
    stochastic_k, stochastic_d = ta.STOCHASTIC(high, low, close, 3, 2)
    obv = ta.OBV(close, volume)

    columns = [
        ("Close", close), ("OBV", obv), ("ADX", adx), ("ADL", adl),
        ("ArUp", aroon_up), ("ArDn", aroon_down), ("MACD", macd),
        ("Signal", signal), ("Hist", histogram), ("RSI", rsi),
        ("%K", stochastic_k), ("%D", stochastic_d),
    ]
    print("\nINDICATOR OUTPUTS (— means the indicator is warming up)\n")
    print("Idx " + " ".join(f"{name:>7}" for name, _ in columns))
    print("--- " + " ".join("-------" for _ in columns))
    for index in range(len(close)):
        print(
            f"{index:>3} "
            + " ".join(format_value(values[index]) for _, values in columns)
        )

    bounded = [adx, aroon_up, aroon_down, rsi, stochastic_k, stochastic_d]
    finite = all(
        value is None or math.isfinite(value)
        for _, values in columns
        for value in values
    )
    in_range = all(
        value is None or 0 <= value <= 100
        for values in bounded
        for value in values
    )
    aligned = all(len(values) == len(close) for _, values in columns)
    print("\nVISIBLE INVARIANTS")
    print(f"  All outputs aligned to {len(close)} input bars: {aligned}")
    print(f"  Every calculated value is finite:          {finite}")
    print(f"  Bounded indicators stay within 0–100:      {in_range}")


def run_suite() -> bool:
    print("\nAUTOMATED VALIDATION\n")
    tests = Path(__file__).resolve().parents[2] / "packages/technical-indicators/tests"
    suite = unittest.defaultTestLoader.discover(str(tests))
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    return result.wasSuccessful()


def main() -> int:
    close = [10, 11, 12, 11, 13, 14, 12, 15, 14, 16, 17, 15]
    high = [value + 1 for value in close]
    low = [value - 1 for value in close]
    volume = [100, 120, 110, 140, 150, 130, 160, 170, 155, 180, 190, 175]
    print_table(close, high, low, volume)
    passed = run_suite()
    print("\nOVERALL RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
