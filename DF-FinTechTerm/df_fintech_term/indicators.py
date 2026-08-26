"""A dependency-free collection of common technical analysis indicators.

The package provides OBV, ADX, ADL, Aroon, MACD, RSI, and the stochastic
oscillator.  Inputs may be lists, tuples, or other finite sequences containing
``int`` and ``float`` values.  Each returned series is aligned by index with
the input series.  Indicators that need a warm-up period put ``None`` at
indices where no value can be calculated yet.

Functions are available under descriptive PEP 8 names and familiar uppercase
aliases.  For example, these calls are equivalent::

    >>> from df_fintech_term import indicators as ta
    >>> ta.obv([10, 11, 10], [100, 150, 120])
    [0.0, 150.0, 30.0]
    >>> ta.OBV([10, 11, 10], [100, 150, 120])
    [0.0, 150.0, 30.0]

Use ``help(df_fintech_term.indicators)`` to see the complete public API, or pass
an individual function such as ``help(df_fintech_term.indicators.OBV)``.

Notes:
    No external packages are required.  Calculations return new lists and do
    not modify their inputs.  All input numbers must be finite; NaN and
    infinity are rejected.  Numeric strings and booleans are not accepted.
    OHLC inputs must describe valid bars: ``low <= close <= high``.
"""

from __future__ import annotations

from math import fsum, isfinite
from numbers import Real
from typing import NamedTuple, Optional, Sequence


Number = int | float
Indicator = list[Optional[float]]


class MACDResult(NamedTuple):
    """Three aligned output series returned by :func:`macd`.

    Attributes:
        macd: The fast EMA minus the slow EMA.
        signal: The EMA of the available MACD values.
        histogram: The MACD line minus the signal line.

    The result supports named attribute access and tuple unpacking::

        >>> lines = macd(list(range(40)))
        >>> macd_line, signal_line, histogram = lines
        >>> lines.macd is macd_line
        True
    """

    macd: Indicator
    signal: Indicator
    histogram: Indicator


class StochasticResult(NamedTuple):
    """Two aligned output series returned by :func:`stochastic_oscillator`.

    Attributes:
        k: The fast stochastic %K line.
        d: The simple moving average of %K.

    The result supports both named attribute access and tuple unpacking.
    """

    k: Indicator
    d: Indicator


def _values(name: str, values: Sequence[Number]) -> list[float]:
    """Validate and copy a finite, real-valued input series.

    Numeric strings and booleans are deliberately rejected.  Silently coercing
    either is hazardous at an ingestion boundary: ``bool`` is an ``int``
    subclass and strings often indicate that parsing/locale handling was
    skipped upstream.
    """
    try:
        iterator = iter(values)
    except TypeError as error:
        raise ValueError(
            f"{name} must be a finite sequence of numeric values"
        ) from error

    result: list[float] = []
    for index, value in enumerate(iterator):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(
                f"{name}[{index}] must be a real number, got {type(value).__name__}"
            )
        try:
            result.append(float(value))
        except OverflowError as error:
            raise ValueError(
                f"{name}[{index}] is too large to represent as a float"
            ) from error
    if any(not isfinite(value) for value in result):
        raise ValueError(f"{name} must contain only finite values")
    return result


def _period(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _same_length(**series: Sequence[Number]) -> None:
    try:
        lengths = {len(values) for values in series.values()}
    except TypeError as error:
        raise ValueError("all inputs must be finite sequences") from error
    if len(lengths) > 1:
        details = ", ".join(f"{name}={len(values)}" for name, values in series.items())
        raise ValueError(f"all input sequences must have the same length ({details})")


def _validate_bars(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float] | None = None,
) -> None:
    """Reject impossible OHLC observations before calculating an indicator."""
    for index, (high, low) in enumerate(zip(highs, lows)):
        if high < low:
            raise ValueError(
                f"high[{index}] must be greater than or equal to low[{index}]"
            )
        if closes is not None and not low <= closes[index] <= high:
            raise ValueError(
                f"close[{index}] must be between low[{index}] and high[{index}]"
            )


def _calculated(name: str, index: int, value: float) -> float:
    """Prevent numerical overflow from escaping as a plausible data point."""
    if not isfinite(value):
        raise OverflowError(
            f"{name}[{index}] is not finite; input magnitudes are too large"
        )
    return value


def _ema(values: Sequence[float], period: int) -> Indicator:
    """Return an SMA-seeded exponential moving average."""
    result: Indicator = [None] * len(values)
    if len(values) < period:
        return result
    current = _calculated("ema", period - 1, fsum(values[:period]) / period)
    result[period - 1] = current
    multiplier = 2.0 / (period + 1)
    for index in range(period, len(values)):
        current = _calculated(
            "ema", index, current + (values[index] - current) * multiplier
        )
        result[index] = current
    return result


def obv(close: Sequence[Number], volume: Sequence[Number]) -> Indicator:
    """Calculate On-Balance Volume (OBV), starting at zero.

    OBV adds the current period's volume when its close is above the previous
    close and subtracts it when the close is below the previous close.  Volume
    is unchanged when consecutive closes are equal.

    Args:
        close: Closing prices in chronological order.
        volume: Non-negative volume for each corresponding closing price.

    Returns:
        A list of cumulative OBV values with the same length as ``close``.  The
        first value is ``0.0``.  Empty inputs return an empty list.

    Raises:
        ValueError: If the inputs differ in length, contain non-numeric or
            non-finite values, or ``volume`` contains a negative value.

    Example:
        >>> obv([10, 11, 10, 10, 12], [100, 150, 120, 90, 200])
        [0.0, 150.0, 30.0, 30.0, 230.0]
    """
    _same_length(close=close, volume=volume)
    closes = _values("close", close)
    volumes = _values("volume", volume)
    for index, value in enumerate(volumes):
        if value < 0:
            raise ValueError(f"volume[{index}] cannot be negative")
    if not closes:
        return []
    result = [0.0]
    for index in range(1, len(closes)):
        direction = (closes[index] > closes[index - 1]) - (
            closes[index] < closes[index - 1]
        )
        result.append(
            _calculated("obv", index, result[-1] + direction * volumes[index])
        )
    return result


def average_directional_index(
    high: Sequence[Number],
    low: Sequence[Number],
    close: Sequence[Number],
    period: int = 14,
) -> Indicator:
    """Calculate Wilder's Average Directional Index (ADX).

    ADX measures trend strength without indicating trend direction.  This
    implementation computes true range and positive/negative directional
    movement, applies Wilder smoothing, and then smooths Directional Index.

    Args:
        high: High prices in chronological order.
        low: Low prices corresponding to ``high``.
        close: Closing prices corresponding to ``high``.
        period: Positive smoothing period.  The conventional default is 14.

    Returns:
        A list aligned with the inputs.  The first usable ADX is at index
        ``2 * period - 1``; earlier entries are ``None``.  ADX values range
        from 0 to 100.  An input shorter than the warm-up returns only
        ``None`` values.

    Raises:
        ValueError: If ``period`` is not a positive integer, input lengths
            differ, a value is invalid, or an OHLC bar is inconsistent.

    Example:
        >>> highs = [value + 1 for value in range(1, 35)]
        >>> lows = [value - 1 for value in range(1, 35)]
        >>> closes = list(range(1, 35))
        >>> average_directional_index(highs, lows, closes)[-1]
        100.0
    """
    _period("period", period)
    _same_length(high=high, low=low, close=close)
    highs = _values("high", high)
    lows = _values("low", low)
    closes = _values("close", close)
    _validate_bars(highs, lows, closes)
    length = len(closes)
    result: Indicator = [None] * length
    if length <= period:
        return result

    true_ranges = [0.0] * length
    plus_dm = [0.0] * length
    minus_dm = [0.0] * length
    for index in range(1, length):
        true_ranges[index] = _calculated(
            "true range",
            index,
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            ),
        )
        upward = _calculated(
            "positive directional movement",
            index,
            highs[index] - highs[index - 1],
        )
        downward = _calculated(
            "negative directional movement",
            index,
            lows[index - 1] - lows[index],
        )
        plus_dm[index] = upward if upward > downward and upward > 0 else 0.0
        minus_dm[index] = downward if downward > upward and downward > 0 else 0.0

    smoothed_tr = fsum(true_ranges[1 : period + 1])
    smoothed_plus = fsum(plus_dm[1 : period + 1])
    smoothed_minus = fsum(minus_dm[1 : period + 1])
    directional_indexes: Indicator = [None] * length

    for index in range(period, length):
        if index > period:
            smoothed_tr = smoothed_tr - smoothed_tr / period + true_ranges[index]
            smoothed_plus = smoothed_plus - smoothed_plus / period + plus_dm[index]
            smoothed_minus = smoothed_minus - smoothed_minus / period + minus_dm[index]
        if smoothed_tr == 0:
            directional_indexes[index] = 0.0
            continue
        plus_di = 100.0 * smoothed_plus / smoothed_tr
        minus_di = 100.0 * smoothed_minus / smoothed_tr
        total = plus_di + minus_di
        directional_indexes[index] = (
            0.0 if total == 0 else 100.0 * abs(plus_di - minus_di) / total
        )

    first_adx = 2 * period - 1
    if length <= first_adx:
        return result
    seed = directional_indexes[period : first_adx + 1]
    current = fsum(value for value in seed if value is not None) / period
    result[first_adx] = _calculated("adx", first_adx, current)
    for index in range(first_adx + 1, length):
        dx = directional_indexes[index]
        assert dx is not None
        current = ((period - 1) * current + dx) / period
        result[index] = _calculated("adx", index, current)
    return result


def accumulation_distribution_line(
    high: Sequence[Number],
    low: Sequence[Number],
    close: Sequence[Number],
    volume: Sequence[Number],
) -> Indicator:
    """Calculate the cumulative Accumulation/Distribution Line (ADL).

    For each period, ADL multiplies volume by the close-location value
    ``((close - low) - (high - close)) / (high - low)`` and cumulatively adds
    the result.  A zero-range period contributes zero.

    Args:
        high: High prices in chronological order.
        low: Low prices corresponding to ``high``.
        close: Closing prices corresponding to ``high``.
        volume: Non-negative volume corresponding to ``high``.

    Returns:
        A cumulative list of floats aligned with the inputs.  Empty inputs
        return an empty list; this indicator has no warm-up period.

    Raises:
        ValueError: If input lengths differ, values are invalid, volume is
            negative, or an OHLC bar is inconsistent.

    Example:
        >>> accumulation_distribution_line(
        ...     [12, 13], [8, 9], [11, 10], [100, 200]
        ... )
        [50.0, -50.0]
    """
    _same_length(high=high, low=low, close=close, volume=volume)
    highs = _values("high", high)
    lows = _values("low", low)
    closes = _values("close", close)
    volumes = _values("volume", volume)
    _validate_bars(highs, lows, closes)
    for index, value in enumerate(volumes):
        if value < 0:
            raise ValueError(f"volume[{index}] cannot be negative")
    result: Indicator = []
    total = 0.0
    for high_value, low_value, close_value, volume_value in zip(
        highs, lows, closes, volumes
    ):
        spread = _calculated("price range", len(result), high_value - low_value)
        multiplier = 0.0 if spread == 0 else (
            (close_value - low_value) - (high_value - close_value)
        ) / spread
        total = _calculated("adl", len(result), total + multiplier * volume_value)
        result.append(total)
    return result


def aroon_indicator(
    high: Sequence[Number],
    low: Sequence[Number],
    period: int = 25,
) -> tuple[Indicator, Indicator]:
    """Calculate Aroon Up and Aroon Down.

    Aroon Up measures how recently the rolling window made its highest high;
    Aroon Down does the same for its lowest low.  When an extreme repeats, the
    most recent occurrence is used.

    Args:
        high: High prices in chronological order.
        low: Low prices corresponding to ``high``.
        period: Positive lookback period.  The conventional default is 25.
            Each calculation examines ``period + 1`` observations.

    Returns:
        A two-item tuple ``(aroon_up, aroon_down)``.  Both lists align with the
        inputs, contain values from 0 to 100, and have ``None`` in their first
        ``period`` positions.

    Raises:
        ValueError: If ``period`` is not a positive integer, input lengths
            differ, values are invalid, or any high is below its matching low.

    Example:
        >>> up, down = aroon_indicator([1, 2, 3, 4], [0, 1, 2, 3], period=3)
        >>> (up[-1], down[-1])
        (100.0, 0.0)
    """
    _period("period", period)
    _same_length(high=high, low=low)
    highs = _values("high", high)
    lows = _values("low", low)
    _validate_bars(highs, lows)
    up: Indicator = [None] * len(highs)
    down: Indicator = [None] * len(highs)
    for index in range(period, len(highs)):
        start = index - period
        high_window = highs[start : index + 1]
        low_window = lows[start : index + 1]
        # The most recent occurrence wins when an extreme is repeated.
        highest = max(high_window)
        lowest = min(low_window)
        high_index = max(
            i for i, value in enumerate(high_window) if value == highest
        )
        low_index = max(i for i, value in enumerate(low_window) if value == lowest)
        up[index] = 100.0 * high_index / period
        down[index] = 100.0 * low_index / period
    return up, down


def macd(
    close: Sequence[Number],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResult:
    """Calculate Moving Average Convergence/Divergence (MACD).

    The MACD line is the fast exponential moving average (EMA) minus the slow
    EMA.  The signal is an EMA of the MACD line, and the histogram is MACD
    minus signal.  EMAs are seeded with a simple moving average.

    Args:
        close: Closing prices in chronological order.
        fast_period: Positive period for the faster EMA.  Defaults to 12.
        slow_period: Positive period for the slower EMA.  Defaults to 26 and
            must be greater than ``fast_period``.
        signal_period: Positive period for the signal EMA.  Defaults to 9.

    Returns:
        A :class:`MACDResult` with ``macd``, ``signal``, and ``histogram``
        lists aligned with ``close``.  The MACD line begins at index
        ``slow_period - 1``.  Signal and histogram begin at index
        ``slow_period + signal_period - 2``; preceding entries are ``None``.

    Raises:
        ValueError: If a period is invalid, ``fast_period`` is not less than
            ``slow_period``, or ``close`` contains an invalid value.

    Example:
        >>> result = macd(list(range(40)))
        >>> len(result.macd) == len(result.signal) == len(result.histogram)
        True
        >>> result.histogram[-1] is not None
        True
    """
    for name, value in (
        ("fast_period", fast_period),
        ("slow_period", slow_period),
        ("signal_period", signal_period),
    ):
        _period(name, value)
    if fast_period >= slow_period:
        raise ValueError("fast_period must be less than slow_period")
    closes = _values("close", close)
    fast = _ema(closes, fast_period)
    slow = _ema(closes, slow_period)
    line: Indicator = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow)):
        line.append(
            None
            if fast_value is None or slow_value is None
            else _calculated("macd", index, fast_value - slow_value)
        )
    available = [value for value in line if value is not None]
    signal_values = _ema(available, signal_period)
    signal: Indicator = [None] * len(closes)
    offset = slow_period - 1
    for index, value in enumerate(signal_values):
        signal[offset + index] = value
    histogram: Indicator = []
    for index, (line_value, signal_value) in enumerate(zip(line, signal)):
        histogram.append(
            None
            if line_value is None or signal_value is None
            else _calculated("macd histogram", index, line_value - signal_value)
        )
    return MACDResult(line, signal, histogram)


def rsi(close: Sequence[Number], period: int = 14) -> Indicator:
    """Calculate Wilder's Relative Strength Index (RSI).

    RSI compares Wilder-smoothed average gains and losses and is bounded from
    0 to 100.  A rising series approaches 100, a falling series approaches 0,
    and a series with no gains or losses returns 50.

    Args:
        close: Closing prices in chronological order.
        period: Positive smoothing period.  The conventional default is 14.

    Returns:
        A list aligned with ``close``.  The first ``period`` entries are
        ``None`` and the first RSI is at index ``period``.  If there are too
        few observations, every entry is ``None``.

    Raises:
        ValueError: If ``period`` is not a positive integer or ``close``
            contains a non-numeric or non-finite value.

    Example:
        >>> rsi([1, 2, 3, 4], period=2)
        [None, None, 100.0, 100.0]
    """
    _period("period", period)
    closes = _values("close", close)
    result: Indicator = [None] * len(closes)
    if len(closes) <= period:
        return result
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    average_gain = fsum(max(change, 0.0) for change in changes[:period]) / period
    average_loss = fsum(max(-change, 0.0) for change in changes[:period]) / period

    def value() -> float:
        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + average_gain / average_loss)

    result[period] = _calculated("rsi", period, value())
    for index in range(period + 1, len(closes)):
        change = changes[index - 1]
        average_gain = ((period - 1) * average_gain + max(change, 0.0)) / period
        average_loss = ((period - 1) * average_loss + max(-change, 0.0)) / period
        result[index] = _calculated("rsi", index, value())
    return result


def stochastic_oscillator(
    high: Sequence[Number],
    low: Sequence[Number],
    close: Sequence[Number],
    k_period: int = 14,
    d_period: int = 3,
) -> StochasticResult:
    """Calculate the fast stochastic oscillator's %K and %D lines.

    Percent K locates the current close within the recent high-low range:
    ``100 * (close - lowest low) / (highest high - lowest low)``.  Percent D
    is a simple moving average of %K.  A zero-range window produces %K of zero.

    Args:
        high: High prices in chronological order.
        low: Low prices corresponding to ``high``.
        close: Closing prices corresponding to ``high``.
        k_period: Positive lookback used by %K.  Defaults to 14.
        d_period: Positive simple-moving-average period for %D.  Defaults to 3.

    Returns:
        A :class:`StochasticResult` containing aligned ``k`` and ``d`` lists.
        Percent K begins at index ``k_period - 1`` and %D begins at index
        ``k_period + d_period - 2``.  Earlier positions are ``None``.

    Raises:
        ValueError: If a period is not a positive integer, input lengths
            differ, values are invalid, or an OHLC bar is inconsistent.

    Example:
        >>> result = stochastic_oscillator(
        ...     [3, 4, 5, 6], [1, 2, 3, 4], [2, 3, 4, 5],
        ...     k_period=2, d_period=2,
        ... )
        >>> result.k
        [None, 66.66666666666667, 66.66666666666667, 66.66666666666667]
        >>> result.d[-1]
        66.66666666666667
    """
    _period("k_period", k_period)
    _period("d_period", d_period)
    _same_length(high=high, low=low, close=close)
    highs = _values("high", high)
    lows = _values("low", low)
    closes = _values("close", close)
    _validate_bars(highs, lows, closes)
    k: Indicator = [None] * len(closes)
    d: Indicator = [None] * len(closes)
    for index in range(k_period - 1, len(closes)):
        start = index - k_period + 1
        highest = max(highs[start : index + 1])
        lowest = min(lows[start : index + 1])
        spread = _calculated("stochastic range", index, highest - lowest)
        raw_k = (
            0.0
            if spread == 0
            else 100.0 * (closes[index] - lowest) / spread
        )
        raw_k = _calculated("stochastic %K", index, raw_k)
        # The bar validation mathematically guarantees this range.  Clamping
        # only removes tiny IEEE-754 excursions at the endpoints.
        k[index] = min(100.0, max(0.0, raw_k))
        if index >= k_period + d_period - 2:
            window = k[index - d_period + 1 : index + 1]
            d[index] = _calculated(
                "stochastic %D",
                index,
                fsum(value for value in window if value is not None) / d_period,
            )
    return StochasticResult(k, d)


# Conventional indicator abbreviations are provided for interactive use.  The
# lowercase descriptive names remain the canonical Python API.  Aliasing the
# same function object keeps signatures, type hints, and help text identical.
OBV = obv
ADX = average_directional_index
ADL = accumulation_distribution_line
AROON = aroon_indicator
MACD = macd
RSI = rsi
STOCHASTIC = stochastic_oscillator


__all__ = [
    "ADL",
    "ADX",
    "AROON",
    "MACD",
    "MACDResult",
    "OBV",
    "RSI",
    "STOCHASTIC",
    "StochasticResult",
    "accumulation_distribution_line",
    "aroon_indicator",
    "average_directional_index",
    "macd",
    "obv",
    "rsi",
    "stochastic_oscillator",
]
