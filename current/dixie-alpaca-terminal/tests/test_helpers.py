import unittest
from pathlib import Path
import subprocess
import io
import json
from unittest.mock import patch

from alpaca_terminal.config import Config, _csv
from alpaca_terminal.finance_tools import FINANCE_TOOLS, build_command, catalog_keys
from alpaca_terminal.local_llm import LOCAL_LLM_MODEL, LocalLLM, LocalLLMError
from alpaca_terminal.ui import Terminal, clip, money, number


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
            "alpaca-analysis",
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

    def test_local_llm_uses_one_fixed_model_and_conversation_history(self):
        response = io.BytesIO(b'{"message":{"role":"assistant","content":"Local reply"}}')
        with patch("alpaca_terminal.local_llm.urlopen", return_value=response) as send:
            reply = LocalLLM().chat([
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "Second"},
                {"role": "user", "content": "Third"},
            ])
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], LOCAL_LLM_MODEL)
        self.assertFalse(payload["stream"])
        self.assertEqual([message["role"] for message in payload["messages"]],
                         ["system", "user", "assistant", "user"])
        self.assertEqual(reply, "Local reply")

    def test_local_llm_rejects_empty_responses(self):
        with patch("alpaca_terminal.local_llm.urlopen",
                   return_value=io.BytesIO(b'{"message":{"content":""}}')):
            with self.assertRaises(LocalLLMError):
                LocalLLM().chat([{"role": "user", "content": "Hello"}])

    def test_tab_switches_between_news_and_local_chat(self):
        terminal = Terminal(Config("key", "secret", "", False, (), 3))
        self.assertEqual(terminal.state.right_pane, "news")
        terminal._key(None, 9)
        self.assertEqual(terminal.state.right_pane, "chat")
        terminal._key(None, 9)
        self.assertEqual(terminal.state.right_pane, "news")


if __name__ == "__main__":
    unittest.main()
