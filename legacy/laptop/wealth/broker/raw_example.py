"""Print raw indicator results for a realistic, deterministic fake market.

This is intentionally not a unit test.  It exposes the exact source candles,
parameters, and unrounded Python results so a person can audit them directly.
"""

from __future__ import annotations

from pprint import pprint

import technical_analysis as ta


# A hand-authored synthetic daily market: an initial climb, a selloff, a
# recovery, consolidation, and a breakout.  Nothing is downloaded or hidden.
DATE = [
    "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07",
    "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14",
    "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21",
    "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28",
    "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04",
    "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11",
    "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18",
]
OPEN = [
    100.00, 100.90, 101.45, 102.30, 103.10, 103.80, 104.10, 103.40, 102.20,
    100.90, 99.80, 98.60, 97.70, 98.20, 99.10, 100.30, 101.10, 102.00,
    101.70, 102.40, 103.20, 103.00, 103.70, 104.10, 103.80, 104.30, 105.00,
    105.80, 106.20, 105.70, 106.40, 107.10, 108.00, 109.20, 110.10,
]
HIGH = [
    101.20, 102.00, 102.80, 103.60, 104.20, 104.70, 104.50, 103.80, 102.70,
    101.40, 100.20, 99.00, 98.50, 99.20, 100.50, 101.50, 102.20, 102.60,
    102.80, 103.50, 103.80, 103.90, 104.40, 104.60, 104.70, 105.40, 106.10,
    106.50, 106.60, 106.40, 107.30, 108.20, 109.40, 110.30, 111.60,
]
LOW = [
    99.50, 100.60, 101.20, 102.00, 102.80, 103.30, 103.20, 102.30, 100.80,
    99.50, 98.40, 97.50, 96.80, 97.80, 98.70, 99.80, 100.70, 101.20,
    101.30, 101.90, 102.60, 102.50, 103.10, 103.40, 103.50, 103.90, 104.60,
    105.20, 105.40, 105.10, 106.00, 106.70, 107.50, 108.80, 109.70,
]
CLOSE = [
    100.80, 101.60, 102.40, 103.20, 103.90, 104.20, 103.50, 102.60, 101.10,
    100.00, 98.90, 97.80, 98.10, 98.80, 100.10, 101.20, 101.80, 102.10,
    102.50, 103.10, 103.00, 103.60, 104.00, 103.90, 104.40, 105.10, 105.90,
    106.00, 105.80, 106.20, 107.00, 107.90, 109.10, 109.80, 111.20,
]
VOLUME = [
    1_120_000, 1_080_000, 1_240_000, 1_310_000, 1_180_000, 1_050_000,
    1_420_000, 1_680_000, 2_050_000, 1_920_000, 2_200_000, 2_480_000,
    2_150_000, 1_760_000, 1_890_000, 1_540_000, 1_320_000, 1_210_000,
    1_090_000, 1_260_000, 980_000, 1_140_000, 1_020_000, 930_000,
    1_170_000, 1_350_000, 1_460_000, 1_110_000, 1_040_000, 1_280_000,
    1_510_000, 1_660_000, 1_940_000, 2_130_000, 2_650_000,
]


def show(name: str, value) -> None:
    print(f"\n{name} =")
    pprint(value, width=120, sort_dicts=False)


def main() -> None:
    print("SYNTHETIC DAILY OHLCV — EXACT RAW VALUES")
    print("This data is fake, deterministic, and designed to resemble real candles.")
    print("All result arrays use the same index as DATE. No value is rounded.\n")

    show("DATE", DATE)
    show("OPEN (informational; indicators do not consume it)", OPEN)
    show("HIGH", HIGH)
    show("LOW", LOW)
    show("CLOSE", CLOSE)
    show("VOLUME", VOLUME)

    show("OBV(close, volume)", ta.OBV(CLOSE, VOLUME))
    show("ADX(high, low, close, period=14)", ta.ADX(HIGH, LOW, CLOSE, period=14))
    show("ADL(high, low, close, volume)", ta.ADL(HIGH, LOW, CLOSE, VOLUME))

    aroon_up, aroon_down = ta.AROON(HIGH, LOW, period=14)
    show("AROON_UP(high, low, period=14)", aroon_up)
    show("AROON_DOWN(high, low, period=14)", aroon_down)

    macd = ta.MACD(CLOSE, fast_period=12, slow_period=26, signal_period=9)
    show("MACD_LINE(close, 12, 26, 9)", macd.macd)
    show("MACD_SIGNAL(close, 12, 26, 9)", macd.signal)
    show("MACD_HISTOGRAM(close, 12, 26, 9)", macd.histogram)

    show("RSI(close, period=14)", ta.RSI(CLOSE, period=14))

    stochastic = ta.STOCHASTIC(HIGH, LOW, CLOSE, k_period=14, d_period=3)
    show("STOCHASTIC_K(high, low, close, 14, 3)", stochastic.k)
    show("STOCHASTIC_D(high, low, close, 14, 3)", stochastic.d)

    print("\nONE-BAR OBV AUDIT")
    print("At index 1, close rose from 100.8 to 101.6.")
    print("OBV[1] = OBV[0] + VOLUME[1] = 0 + 1,080,000 = 1,080,000.")
    print("At index 6, close fell from 104.2 to 103.5, so volume is subtracted.")
    print("\nONE-BAR ADL AUDIT (index 0)")
    multiplier = ((CLOSE[0] - LOW[0]) - (HIGH[0] - CLOSE[0])) / (
        HIGH[0] - LOW[0]
    )
    print(
        "multiplier = ((close-low) - (high-close)) / (high-low) =",
        repr(multiplier),
    )
    print("ADL[0] = multiplier * volume =", repr(multiplier * VOLUME[0]))


if __name__ == "__main__":
    main()
