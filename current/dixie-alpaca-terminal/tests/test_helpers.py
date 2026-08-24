import unittest

from alpaca_terminal.config import Config, _csv
from alpaca_terminal.ui import clip, money, number


class HelperTests(unittest.TestCase):
    def test_csv_normalizes_and_deduplicates(self):
        self.assertEqual(_csv(" spy, AAPL,spy "), ("SPY", "AAPL"))

    def test_formatters(self):
        self.assertEqual(money("1234.5"), "1,234.50")
        self.assertEqual(money("-2", True), "-2.00")
        self.assertEqual(number("1.2500"), "1.25")
        self.assertEqual(money(None), "--")

    def test_clip(self):
        self.assertEqual(clip("abcdef", 4), "abc…")
        self.assertEqual(clip("abc", 4), "abc")


if __name__ == "__main__":
    unittest.main()
