"""Dependency-free correctness and contract tests for every public indicator."""

from __future__ import annotations

import math
import unittest

from df_fintech_term import indicators as ta


class IndicatorAssertions(unittest.TestCase):
    def assertSeriesAlmostEqual(self, actual, expected, places=10):
        self.assertEqual(len(actual), len(expected))
        for index, (observed, wanted) in enumerate(zip(actual, expected)):
            with self.subTest(index=index):
                if wanted is None:
                    self.assertIsNone(observed)
                else:
                    self.assertIsNotNone(observed)
                    self.assertAlmostEqual(observed, wanted, places=places)

    def assertFiniteSeries(self, values):
        for index, value in enumerate(values):
            with self.subTest(index=index):
                self.assertTrue(value is None or math.isfinite(value))


class OBVTests(IndicatorAssertions):
    def test_known_answer_with_rises_falls_and_ties(self):
        self.assertEqual(
            ta.obv([10, 11, 10, 10, 12], [100, 150, 120, 90, 200]),
            [0.0, 150.0, 30.0, 30.0, 230.0],
        )

    def test_empty_and_single_observation(self):
        self.assertEqual(ta.obv([], []), [])
        self.assertEqual(ta.obv([10], [999]), [0.0])

    def test_inputs_are_not_modified(self):
        close = [10, 11, 9]
        volume = [4, 5, 6]
        originals = (close.copy(), volume.copy())
        ta.obv(close, volume)
        self.assertEqual((close, volume), originals)


class ADXTests(IndicatorAssertions):
    def test_steady_uptrend_reaches_one_hundred(self):
        close = list(range(1, 35))
        high = [value + 1 for value in close]
        low = [value - 1 for value in close]
        result = ta.average_directional_index(high, low, close, period=14)
        self.assertEqual(result[:27], [None] * 27)
        self.assertEqual(result[27:], [100.0] * 7)

    def test_flat_market_is_zero_after_warmup(self):
        values = [10.0] * 12
        result = ta.ADX(values, values, values, period=3)
        self.assertEqual(result[:5], [None] * 5)
        self.assertEqual(result[5:], [0.0] * 7)

    def test_too_short_is_all_warmup(self):
        self.assertEqual(ta.ADX([2, 3], [0, 1], [1, 2], 2), [None, None])


class ADLTests(IndicatorAssertions):
    def test_known_money_flow_answer(self):
        self.assertEqual(
            ta.accumulation_distribution_line(
                [12, 13, 10], [8, 9, 10], [11, 10, 10], [100, 200, 50]
            ),
            [50.0, -50.0, -50.0],
        )

    def test_close_at_extremes(self):
        self.assertEqual(ta.ADL([2, 2], [0, 0], [2, 0], [10, 10]), [10.0, 0.0])

    def test_empty(self):
        self.assertEqual(ta.ADL([], [], [], []), [])


class AroonTests(IndicatorAssertions):
    def test_rising_market(self):
        up, down = ta.aroon_indicator([1, 2, 3, 4], [0, 1, 2, 3], period=3)
        self.assertEqual(up, [None, None, None, 100.0])
        self.assertEqual(down, [None, None, None, 0.0])

    def test_most_recent_repeated_extreme_wins(self):
        up, down = ta.AROON([5, 5, 4], [1, 2, 1], period=2)
        self.assertEqual(up[-1], 50.0)
        self.assertEqual(down[-1], 100.0)

    def test_outputs_are_bounded(self):
        up, down = ta.AROON([3, 1, 4, 2, 5], [2, 0, 3, 1, 4], period=2)
        for series in (up, down):
            self.assertTrue(all(value is None or 0 <= value <= 100 for value in series))


class MACDTests(IndicatorAssertions):
    def test_hand_calculated_linear_series(self):
        result = ta.macd([1, 2, 3, 4, 5, 6], 2, 3, 2)
        self.assertSeriesAlmostEqual(result.macd, [None, None, 0.5, 0.5, 0.5, 0.5])
        self.assertSeriesAlmostEqual(result.signal, [None, None, None, 0.5, 0.5, 0.5])
        self.assertSeriesAlmostEqual(result.histogram, [None, None, None, 0, 0, 0])

    def test_constant_series_is_zero(self):
        result = ta.MACD([7.0] * 12, 2, 4, 3)
        self.assertTrue(all(value in (None, 0.0) for value in result.macd))
        self.assertTrue(all(value in (None, 0.0) for value in result.signal))
        self.assertTrue(all(value in (None, 0.0) for value in result.histogram))

    def test_named_access_and_unpacking(self):
        result = ta.MACD(range(20), 3, 5, 2)
        line, signal, histogram = result
        self.assertIs(line, result.macd)
        self.assertIs(signal, result.signal)
        self.assertIs(histogram, result.histogram)


class RSITests(IndicatorAssertions):
    def test_wilder_reference_example(self):
        # Classic 14-period Wilder worksheet data.  The first published RSI is
        # approximately 70.4641.
        close = [
            44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
            45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
        ]
        result = ta.rsi(close)
        self.assertEqual(result[:14], [None] * 14)
        self.assertAlmostEqual(result[14], 70.4641350211, places=9)

    def test_monotonic_and_flat_series(self):
        self.assertEqual(ta.RSI([1, 2, 3, 4], 2), [None, None, 100.0, 100.0])
        self.assertEqual(ta.RSI([4, 3, 2, 1], 2), [None, None, 0.0, 0.0])
        self.assertEqual(ta.RSI([2, 2, 2, 2], 2), [None, None, 50.0, 50.0])

    def test_is_bounded(self):
        result = ta.RSI([10, 11, 9, 13, 8, 12, 7, 15, 14], 3)
        self.assertTrue(all(value is None or 0 <= value <= 100 for value in result))


class StochasticTests(IndicatorAssertions):
    def test_hand_calculated_answer(self):
        result = ta.stochastic_oscillator(
            [3, 4, 5, 6], [1, 2, 3, 4], [2, 3, 4, 5], 2, 2
        )
        expected_k = [None, 200 / 3, 200 / 3, 200 / 3]
        self.assertSeriesAlmostEqual(result.k, expected_k)
        self.assertSeriesAlmostEqual(result.d, [None, None, 200 / 3, 200 / 3])

    def test_window_extremes_and_zero_range(self):
        result = ta.STOCHASTIC([2, 3, 3], [1, 1, 3], [1, 3, 3], 1, 1)
        self.assertEqual(result.k, [0.0, 100.0, 0.0])
        self.assertEqual(result.d, result.k)

    def test_named_access_and_bounds(self):
        result = ta.STOCHASTIC([2, 4, 3], [0, 1, 2], [1, 4, 2], 2, 2)
        k, d = result
        self.assertIs(k, result.k)
        self.assertIs(d, result.d)
        self.assertTrue(all(value is None or 0 <= value <= 100 for value in k + d))


class ValidationContractTests(IndicatorAssertions):
    def test_period_validation_for_all_period_arguments(self):
        calls = [
            lambda p: ta.ADX([1], [0], [0.5], p),
            lambda p: ta.AROON([1], [0], p),
            lambda p: ta.RSI([1], p),
            lambda p: ta.MACD([1], p, 2, 1),
            lambda p: ta.STOCHASTIC([1], [0], [0.5], p, 1),
        ]
        for period in (0, -1, 1.5, True):
            for call in calls:
                with self.subTest(period=period, call=call):
                    with self.assertRaises(ValueError):
                        call(period)

    def test_macd_period_relationship(self):
        with self.assertRaisesRegex(ValueError, "fast_period must be less"):
            ta.MACD([1, 2], 3, 3, 1)

    def test_mismatched_lengths_for_multiseries_indicators(self):
        calls = [
            lambda: ta.OBV([1], []),
            lambda: ta.ADX([1], [0], []),
            lambda: ta.ADL([1], [0], [0.5], []),
            lambda: ta.AROON([1], []),
            lambda: ta.STOCHASTIC([1], [0], []),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_nonfinite_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ta.RSI([1.0, value], 1)

    def test_implicit_coercions_are_rejected(self):
        for value in (True, False, "1.0", None, object()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ta.OBV([1.0, value], [1.0, 1.0])

    def test_negative_volume_is_rejected(self):
        for call in (
            lambda: ta.OBV([1], [-1]),
            lambda: ta.ADL([1], [0], [0.5], [-1]),
        ):
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_impossible_bars_are_rejected(self):
        calls = [
            lambda: ta.ADX([0], [1], [0.5], 1),
            lambda: ta.ADL([1], [0], [2], [1]),
            lambda: ta.AROON([0], [1], 1),
            lambda: ta.STOCHASTIC([1], [0], [-1], 1, 1),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()

    def test_overflow_is_rejected_instead_of_returned(self):
        with self.assertRaises(OverflowError):
            ta.OBV([1, 2, 3], [1.7e308] * 3)
        with self.assertRaises(OverflowError):
            ta.ADL([2, 2], [0, 0], [2, 2], [1.7e308] * 2)

    def test_every_public_alias_is_the_canonical_function(self):
        aliases = {
            "OBV": "obv",
            "ADX": "average_directional_index",
            "ADL": "accumulation_distribution_line",
            "AROON": "aroon_indicator",
            "MACD": "macd",
            "RSI": "rsi",
            "STOCHASTIC": "stochastic_oscillator",
        }
        for alias, canonical in aliases.items():
            with self.subTest(alias=alias):
                self.assertIs(getattr(ta, alias), getattr(ta, canonical))

    def test_all_indicators_return_new_finite_aligned_lists(self):
        close = [10, 11, 9, 12, 10, 13, 11, 14, 12, 15]
        high = [value + 1 for value in close]
        low = [value - 1 for value in close]
        volume = list(range(100, 110))
        outputs = [
            ta.OBV(close, volume),
            ta.ADX(high, low, close, 2),
            ta.ADL(high, low, close, volume),
            *ta.AROON(high, low, 2),
            *ta.MACD(close, 2, 3, 2),
            ta.RSI(close, 2),
            *ta.STOCHASTIC(high, low, close, 2, 2),
        ]
        for output in outputs:
            self.assertIsInstance(output, list)
            self.assertEqual(len(output), len(close))
            self.assertFiniteSeries(output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
