import unittest
from pathlib import Path
import subprocess

from alpaca_terminal.config import Config, _csv
from alpaca_terminal.finance_tools import FINANCE_TOOLS, build_command, catalog_keys
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

    def test_finance_palette_covers_every_shell_operation(self):
        expected = {
            "indicators-test", "indicators-report", "indicators-example",
            "price-bitcoin", "price-silver", "tickrs", "ticker", "tickrs-industry",
            "classify-refresh", "classify-list", "sentiment-analyze", "sentiment-pending",
            "sentiment-list", "alpaca-sync-assets", "alpaca-history",
            "alpaca-history-list", "alpaca-status", "alpaca-news", "alpaca-timeframes",
            "stream-add", "stream-remove", "stream-list", "stream-start", "stream-stop",
            "stream-restart", "stream-status", "stream-view", "calc-compound", "calc-gain",
            "calc-budget", "calc-allocate", "doctor", "help",
        }
        self.assertEqual(catalog_keys(), expected)
        self.assertEqual(len(FINANCE_TOOLS), len(expected))

    def test_finance_command_uses_argv_without_shell_interpretation(self):
        tool = next(item for item in FINANCE_TOOLS if item.key == "alpaca-history")
        command = build_command(
            Path("/opt/finance shell/fsh"),
            tool,
            "'BTC/USD' --class crypto --start '2026-01-01 00:00:00Z'; touch nope",
        )
        self.assertEqual(command[:4],
                         ["/opt/finance shell/fsh", "alpaca", "history", "BTC/USD"])
        self.assertTrue(any(";" in argument for argument in command))
        self.assertEqual(command[-2:], ["touch", "nope"])

    def test_unified_launcher_dispatches_finance_shell(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [str(root / "run.sh"), "fsh", "help"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Finance Shell", result.stdout)
        self.assertIn("alpaca history", result.stdout)


if __name__ == "__main__":
    unittest.main()
