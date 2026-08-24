import curses
import unittest
from pathlib import Path
import subprocess
import io
import json
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from df_fintech_term.config import Config, _csv
from df_fintech_term.api import AlpacaClient
from df_fintech_term.analysis_view import load_active_analysis
from df_fintech_term.finance_tools import FINANCE_TOOLS, build_command, catalog_keys
from df_fintech_term.industry_view import load_industries, tickrs_command
from df_fintech_term.local_llm import LOCAL_LLM_MODEL, LocalLLM, LocalLLMError
from df_fintech_term.news_feed import load_live_news, merge_news
from df_fintech_term.watchlist_view import load_stream_watchlist, unique_symbols
from df_fintech_term.ui import Terminal, clip, money, number, sellable_symbols


class HelperTests(unittest.TestCase):
    def test_csv_normalizes_and_deduplicates(self):
        self.assertEqual(_csv(" spy, AAPL,spy "), ("SPY", "AAPL"))

    def test_formatters(self):
        self.assertEqual(money("1234.5"), "1,234.50")
        self.assertEqual(money("-2", True), "-2.00")
        self.assertEqual(number("1.2500"), "1.25")
        self.assertEqual(money(None), "--")

    def test_sellable_symbols_only_returns_positive_holdings(self):
        positions = [
            {"symbol": "AAPL", "qty": "2"},
            {"symbol": "MSFT", "qty": "0"},
            {"symbol": "TSLA", "qty": "-3"},
            {"symbol": "aapl", "qty": "1"},
            {"symbol": "BAD", "qty": "unknown"},
        ]
        self.assertEqual(sellable_symbols(positions), ["AAPL"])

    def test_sell_dialog_blocks_symbols_not_held(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        terminal.state.positions = [{"symbol": "AAPL", "qty": "2"}]
        with patch.object(terminal, "_prompt", return_value="MSFT"), \
             patch.object(terminal.alpaca, "place_order") as place:
            terminal._order_dialog(None, "sell")
        place.assert_not_called()
        self.assertIn("not a positive account holding", terminal.state.status)

    def test_buy_dialog_accepts_symbol_outside_positions(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        terminal.state.positions = [{"symbol": "AAPL", "qty": "2"}]
        with patch.object(terminal, "_prompt", side_effect=("MSFT", "1", "market")), \
             patch.object(terminal, "_confirm", return_value=True), \
             patch.object(terminal.alpaca, "place_order", return_value={"id": "12345678"}) as place:
            terminal._order_dialog(None, "buy")
        self.assertEqual(place.call_args.args[0]["symbol"], "MSFT")
        self.assertEqual(place.call_args.args[0]["side"], "buy")

    def test_clip(self):
        self.assertEqual(clip("abcdef", 4), "abc…")
        self.assertEqual(clip("abc", 4), "abc")

    def test_finance_palette_covers_every_shell_operation(self):
        expected = {
            "indicators-test", "indicators-report", "indicators-example",
            "price-bitcoin", "price-silver", "tickrs", "ticker", "tickrs-industry",
            "classify-refresh", "classify-populate-alpaca", "classify-list",
            "alpaca-sync-assets", "alpaca-history",
            "alpaca-history-list", "alpaca-update-history", "alpaca-status", "alpaca-news", "alpaca-timeframes",
            "alpaca-analysis",
            "stream-add", "stream-remove", "stream-list", "stream-start", "stream-stop",
            "stream-restart", "stream-status", "stream-view", "calc-compound", "calc-gain",
            "services", "service-run", "actions", "action-run",
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
        with patch("df_fintech_term.local_llm.urlopen", return_value=response) as send:
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
        with patch("df_fintech_term.local_llm.urlopen",
                   return_value=io.BytesIO(b'{"message":{"content":""}}')):
            with self.assertRaises(LocalLLMError):
                LocalLLM().chat([{"role": "user", "content": "Hello"}])

    def test_tab_switches_between_news_and_local_chat(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        self.assertEqual(terminal.state.right_pane, "news")
        terminal._key(None, 9)
        self.assertEqual(terminal.state.right_pane, "chat")
        terminal._key(None, 9)
        self.assertEqual(terminal.state.right_pane, "watchlist")
        terminal._key(None, 9)
        self.assertEqual(terminal.state.right_pane, "news")

    def test_a_switches_between_dashboard_and_live_analysis(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        self.assertEqual(terminal.state.main_view, "dashboard")
        terminal._key(None, ord("a"))
        self.assertEqual(terminal.state.main_view, "analysis")
        terminal._key(None, ord("a"))
        self.assertEqual(terminal.state.main_view, "dashboard")

    def test_main_tabs_cycle_without_changing_right_panel(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        terminal._key(None, curses.KEY_BTAB)
        self.assertEqual(terminal.state.main_view, "ticker")
        self.assertEqual(terminal.state.right_pane, "news")
        terminal._key(None, curses.KEY_BTAB)
        self.assertEqual(terminal.state.main_view, "industry")
        self.assertEqual(terminal.state.right_pane, "news")
        terminal._key(None, curses.KEY_BTAB)
        self.assertEqual(terminal.state.main_view, "analysis")
        terminal._key(None, curses.KEY_BTAB)
        self.assertEqual(terminal.state.main_view, "dashboard")

    def test_daemon_watchlist_is_loaded_with_subscription_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch.sqlite3"
            db = sqlite3.connect(path)
            db.execute("""
                CREATE TABLE stream_watchlist (
                  asset_class TEXT, symbol TEXT, feed TEXT, location TEXT, added_at TEXT
                )
            """)
            db.executemany("INSERT INTO stream_watchlist VALUES (?,?,?,?,?)", [
                ("stock", "AAPL", "iex", "", "now"),
                ("crypto", "BTC/USD", "", "us", "now"),
            ])
            db.commit()
            db.close()
            entries = load_stream_watchlist(path)
            self.assertEqual(unique_symbols(entries), ["AAPL", "BTC/USD"])
            self.assertEqual(unique_symbols(entries, "stock"), ["AAPL"])
            self.assertEqual(entries[0]["asset_class"], "crypto")

    def test_watchlist_edits_use_stream_controller_and_shared_database(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        completed = MagicMock(returncode=0, stdout="Added stock MSFT\n", stderr="")
        with patch("df_fintech_term.ui.subprocess.run", return_value=completed) as run, \
             patch("df_fintech_term.ui.load_stream_watchlist", return_value=[]):
            self.assertTrue(terminal._stream_watchlist_command(
                "add", {"symbol": "MSFT", "asset_class": "stock"}
            ))
        command = run.call_args.args[0]
        self.assertEqual(command[:3], [str(terminal.config.finance_shell), "alpaca", "stream"])
        self.assertIn(str(terminal.config.finance_database), command)
        self.assertEqual(command[-4:], ["add", "MSFT", "--class", "stock"])

    def test_industry_view_groups_only_classified_symbols_with_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "industry.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE bars (asset_class TEXT, symbol TEXT);
                CREATE TABLE live_trades (asset_class TEXT, symbol TEXT);
                CREATE TABLE live_market_events (asset_class TEXT, symbol TEXT);
                CREATE TABLE live_orderbooks (asset_class TEXT, symbol TEXT);
                CREATE TABLE assets (asset_class TEXT, symbol TEXT, status TEXT);
                CREATE TABLE symbol_classifications (
                  asset_class TEXT, symbol TEXT, industry TEXT, sector TEXT,
                  company_name TEXT, status TEXT
                );
            """)
            db.executemany("INSERT INTO bars VALUES (?, ?)",
                           [("stock", "AAPL"), ("stock", "MSFT")])
            db.executemany("INSERT INTO symbol_classifications VALUES (?,?,?,?,?,?)", [
                ("stock", "MSFT", "Software", "Technology", "Microsoft", "classified"),
                ("stock", "AAPL", "Hardware", "Technology", "Apple", "classified"),
                ("stock", "NONE", "Software", "Technology", "No Data", "classified"),
            ])
            db.commit()
            db.close()

            rows = load_industries(path)
            self.assertEqual([row["industry"] for row in rows], ["Hardware", "Software"])
            self.assertEqual(rows[1]["symbols"], [{"symbol": "MSFT", "company": "Microsoft"}])

    def test_stock_snapshots_are_batched_for_large_industries(self):
        client = AlpacaClient("key", "secret", "https://paper.example")
        symbols = [f"S{index}" for index in range(401)]
        with patch.object(client, "data", side_effect=lambda _path, params: {
            "snapshots": {symbol: {"latestTrade": {"p": 1}}
                          for symbol in params["symbols"].split(",")}
        }) as request:
            snapshots = client.stock_snapshots(symbols)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(set(snapshots), set(symbols))

    def test_industry_builds_exact_tickrs_symbol_interface(self):
        command = tickrs_command({
            "industry": "Software",
            "symbols": [{"symbol": "MSFT"}, {"symbol": "ORCL"}],
        })
        self.assertEqual(command, ["tickrs", "--symbols", "MSFT,ORCL"])

    def test_t_reports_missing_tickrs_without_opening_chat(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        terminal.state.main_view = "industry"
        terminal.state.right_pane = "news"
        terminal.state.industries = [{"industry": "Software", "symbols": [{"symbol": "MSFT"}]}]
        with patch("df_fintech_term.ui.shutil.which", return_value=None), \
             patch.object(terminal, "_chat_dialog") as chat:
            terminal._key(None, ord("t"))
        chat.assert_not_called()
        self.assertIn("tickrs is not installed", terminal.state.status)

    def test_chat_enter_remains_available_from_industry_view(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        terminal.state.main_view = "industry"
        terminal.state.right_pane = "chat"
        with patch.object(terminal, "_chat_dialog") as chat, \
             patch.object(terminal, "_open_industry_ticker") as ticker:
            terminal._key(None, 10)
        chat.assert_called_once()
        ticker.assert_not_called()

    def test_non_dashboard_views_keep_the_right_panel_visible(self):
        terminal = Terminal(Config("key", "secret", False, (), 3))
        screen = MagicMock()
        screen.getmaxyx.return_value = (30, 120)
        with patch("df_fintech_term.ui.curses.color_pair", return_value=0), \
             patch.object(terminal, "_draw_main_tabs"), \
             patch.object(terminal, "_draw_industries") as industry, \
             patch.object(terminal, "_draw_analysis") as analysis, \
             patch.object(terminal, "_draw_news") as news, \
             patch.object(terminal, "_draw_chat") as chat, \
             patch.object(terminal, "_draw_trade_panel") as trade:
            terminal.state.main_view = "industry"
            terminal.state.right_pane = "news"
            terminal._draw(screen)
            industry.assert_called_once()
            news.assert_called_once()
            trade.assert_called_once()

            terminal.state.main_view = "analysis"
            terminal.state.right_pane = "chat"
            terminal._draw(screen)
            analysis.assert_called_once()
            chat.assert_called_once()
            self.assertEqual(trade.call_count, 2)
    def test_indicator_formatter_compacts_large_values(self):
        self.assertEqual(Terminal._indicator(None), "--")
        self.assertEqual(Terminal._indicator(52.125), "52.12")
        self.assertEqual(Terminal._indicator(1_250_000), "1.25M")

    def test_live_analysis_view_filters_and_sorts_active_watched_books(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "analysis.sqlite3"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE stream_watchlist (
                  asset_class TEXT, symbol TEXT, feed TEXT, location TEXT
                );
                CREATE TABLE live_orderbooks (
                  asset_class TEXT, symbol TEXT, feed TEXT, location TEXT
                );
                CREATE TABLE technical_analysis_snapshots (
                  asset_class TEXT, symbol TEXT, feed TEXT, location TEXT,
                  source_trade_id TEXT, trade_timestamp TEXT, bar_timestamp TEXT,
                  bars_buffered INTEGER, indicators_json TEXT, updated_at TEXT
                );
            """)
            now = datetime.now(UTC)
            recent = [
                ("stock", "AAPL", "iex", "", "1", "t", "b", 40,
                 '{"rsi":60}', (now - timedelta(seconds=20)).isoformat()),
                ("stock", "MSFT", "iex", "", "2", "t", "b", 40,
                 '{"rsi":55}', (now - timedelta(seconds=5)).isoformat()),
                ("stock", "OLD", "iex", "", "3", "t", "b", 40,
                 '{"rsi":50}', (now - timedelta(minutes=10)).isoformat()),
                ("stock", "IGNORED", "iex", "", "4", "t", "b", 40,
                 '{"rsi":45}', now.isoformat()),
            ]
            db.executemany("INSERT INTO technical_analysis_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)", recent)
            db.executemany("INSERT INTO live_orderbooks VALUES (?,?,?,?)",
                           [row[:4] for row in recent])
            db.executemany("INSERT INTO stream_watchlist VALUES (?,?,?,?)",
                           [row[:4] for row in recent if row[1] != "IGNORED"])
            db.commit()
            db.close()
            rows = load_active_analysis(path)
            self.assertEqual([row["symbol"] for row in rows], ["MSFT", "AAPL"])
            self.assertEqual(rows[0]["indicators"]["rsi"], 55)

    def test_live_news_merges_both_providers_newest_first(self):
        external = [
            {"timestamp": "2026-08-24T10:00:00Z", "source": "Wire",
             "title": "Older story", "url": "https://example.test/older",
             "provider": "NewsData"},
            {"timestamp": "2026-08-24T12:00:00Z", "source": "Wire",
             "title": "Duplicate story", "url": "https://example.test/shared",
             "provider": "NewsData"},
        ]
        alpaca = [
            {"timestamp": "2026-08-24T13:00:00Z", "source": "Benzinga",
             "title": "Newest story", "url": "https://example.test/new", "provider": "Alpaca"},
            {"timestamp": "2026-08-24T11:00:00Z", "source": "Benzinga",
             "title": "Duplicate story", "url": "https://example.test/shared", "provider": "Alpaca"},
        ]
        merged = merge_news(alpaca, external)
        self.assertEqual([item["title"] for item in merged],
                         ["Newest story", "Duplicate story", "Older story"])
        self.assertEqual(merged[1]["provider"], "NewsData")

    def test_live_news_reads_alpaca_stream_database_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.sqlite3"
            db = sqlite3.connect(path)
            db.execute("""
                CREATE TABLE news_articles (
                  article_id TEXT PRIMARY KEY, headline TEXT, source TEXT,
                  updated_at TEXT, url TEXT
                )
            """)
            db.execute("INSERT INTO news_articles VALUES (?,?,?,?,?)",
                       ("1", "Headline", "Benzinga", "2026-08-24T12:00:00Z", "url"))
            db.commit()
            db.close()
            rows = load_live_news(path)
            self.assertEqual(rows[0]["provider"], "Alpaca")
            self.assertEqual(rows[0]["title"], "Headline")


if __name__ == "__main__":
    unittest.main()
