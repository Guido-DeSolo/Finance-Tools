from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import alpaca_store
import live_stream
import live_analysis
import classify_symbols
import tickrs_industry
import stream_service
import news_sentiment


class AlpacaStoreTests(unittest.TestCase):
    def test_trade_buffer_runs_full_indicator_suite_after_each_trade(self):
        buffer = live_analysis.SymbolBuffer(max_bars=50)
        for minute in range(40):
            buffer.add_trade(
                f"2026-01-01T00:{minute:02d}:30Z", 100 + minute, 10 + minute
            )
        values = buffer.indicators()
        self.assertEqual(set(values), {
            "obv", "adx", "adl", "aroon_up", "aroon_down", "macd",
            "macd_signal", "macd_histogram", "rsi", "stochastic_k", "stochastic_d",
        })
        self.assertEqual(len(buffer.bars), 40)
        self.assertEqual(values["rsi"], 100.0)
        self.assertIsNotNone(values["macd_signal"])
        self.assertIsNotNone(values["adx"])

    def test_live_analyzer_only_buffers_symbols_with_orderbooks(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            watched = {"asset_class": "stock", "symbol": "AAPL", "feed": "iex", "location": "us"}
            ignored = {"asset_class": "stock", "symbol": "MSFT", "feed": "iex", "location": "us"}
            quote = {"T": "q", "S": "AAPL", "t": "2026-01-01T00:00:00Z",
                     "bp": 100, "bs": 2, "ap": 101, "as": 3}
            live_stream.store_book(db, watched, quote)
            for row, trade_id, timestamp, price in (
                (watched, 1, "2026-01-01T00:00:01Z", 100.0),
                (ignored, 2, "2026-01-01T00:00:02Z", 200.0),
            ):
                live_stream.store_trade(db, row, {
                    "T": "t", "S": row["symbol"], "i": trade_id,
                    "t": timestamp, "p": price, "s": 1,
                })
            db.commit()
            analyzer = live_analysis.LiveAnalyzer()
            self.assertEqual(analyzer.cycle(db, warm=True), 1)
            snapshot = db.execute("""
                SELECT symbol, source_trade_id, bars_buffered, indicators_json
                FROM technical_analysis_snapshots
            """).fetchone()
            self.assertEqual(snapshot[:3], ("AAPL", "1", 1))
            self.assertIn("rsi", json.loads(snapshot[3]))

    def history_args(self, database: Path, asset_class: str, symbol: str, **changes):
        values = dict(db=database, asset_class=asset_class, symbol=symbol, timeframe="1Day",
                      start="2026-01-01", end="2026-01-03", feed="iex", adjustment="raw",
                      asof=None, location="us", limit=10000, max_pages=None)
        values.update(changes)
        return argparse.Namespace(**values)

    def test_timeframes(self):
        for value in ("1Min", "59T", "1Hour", "23H", "1Day", "1D", "1Week", "12Month", "6M"):
            self.assertEqual(alpaca_store.normalize_timeframe(value), value)
        for value in ("0Min", "60Min", "24Hour", "2Day", "2Week", "5Month"):
            with self.assertRaises(argparse.ArgumentTypeError):
                alpaca_store.normalize_timeframe(value)
        self.assertEqual(alpaca_store.page_limit("10000"), 10000)
        for value in ("0", "10001", "nope"):
            with self.assertRaises(argparse.ArgumentTypeError):
                alpaca_store.page_limit(value)

    def test_schema_and_bar_upsert(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            args = argparse.Namespace(asset_class="stock", symbol="AAPL", timeframe="1Day",
                                      feed="iex", adjustment="raw")
            bar = {"t": "2026-01-01T00:00:00Z", "o": 1, "h": 3, "l": 1,
                   "c": 2, "v": 10, "n": 2, "vw": 2.1}
            self.assertEqual(alpaca_store.save_bars(db, args, [bar]), 1)
            bar["c"] = 2.5
            alpaca_store.save_bars(db, args, [bar])
            db.commit()
            self.assertEqual(db.execute("SELECT count(*) FROM bars").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT close FROM bars").fetchone()[0], 2.5)

    def test_live_trade_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            db.row_factory = sqlite3.Row
            db.execute("INSERT INTO stream_subscriptions VALUES (?, ?, ?, ?, ?, ?)",
                       ("abc", "crypto", "BTC/USD", "iex", "us", alpaca_store.now()))
            row = db.execute("SELECT * FROM stream_subscriptions").fetchone()
            trade = {"T": "t", "S": "BTC/USD", "p": 60000.5, "s": 0.01,
                     "t": "2026-01-01T00:00:00.123456789Z", "i": 42, "tks": "B"}
            live_stream.store_trade(db, row, trade)
            live_stream.store_trade(db, row, trade)
            db.commit()
            self.assertEqual(db.execute("SELECT count(*) FROM live_trades").fetchone()[0], 1)

    def test_stock_quote_upserts_top_of_book(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            row = {"asset_class": "stock", "symbol": "AAPL", "feed": "iex", "location": "us"}
            quote = {"T": "q", "S": "AAPL", "t": "2026-01-01T00:00:00Z",
                     "bp": 100, "bs": 2, "bx": "V", "ap": 101, "as": 3, "ax": "D"}
            live_stream.store_book(db, row, quote)
            quote.update(t="2026-01-01T00:00:01Z", bp=100.5)
            live_stream.store_book(db, row, quote)
            db.commit()
            result = db.execute("SELECT bids_json, is_full_depth FROM live_orderbooks").fetchone()
            self.assertEqual(db.execute("SELECT count(*) FROM live_orderbooks").fetchone()[0], 1)
            self.assertEqual(json.loads(result[0])[0]["p"], 100.5)
            self.assertEqual(result[1], 0)

    def test_crypto_orderbook_reset_and_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            row = {"asset_class": "crypto", "symbol": "BTC/USD", "feed": "iex", "location": "us"}
            book = {"bids": {}, "asks": {}}
            reset = {"T": "o", "S": "BTC/USD", "t": "2026-01-01T00:00:00Z", "r": True,
                     "b": [{"p": 99, "s": 2}, {"p": 98, "s": 3}],
                     "a": [{"p": 101, "s": 4}]}
            live_stream.store_book(db, row, reset, book)
            delta = {"T": "o", "S": "BTC/USD", "t": "2026-01-01T00:00:01Z",
                     "b": [{"p": 99, "s": 0}, {"p": 100, "s": 1}], "a": []}
            live_stream.store_book(db, row, delta, book)
            db.commit()
            result = db.execute("SELECT bids_json, asks_json, is_full_depth FROM live_orderbooks").fetchone()
            self.assertEqual([level["p"] for level in json.loads(result[0])], [100.0, 98.0])
            self.assertEqual(json.loads(result[1])[0]["p"], 101.0)
            self.assertEqual(result[2], 1)

    def test_raw_market_events_are_append_only_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            row = {"asset_class": "crypto", "symbol": "BTC/USD", "feed": "", "location": "us"}
            first = {"T": "o", "S": "BTC/USD", "t": "2026-01-01T00:00:00Z",
                     "b": [{"p": 99, "s": 2}], "a": []}
            second = {"T": "o", "S": "BTC/USD", "t": "2026-01-01T00:00:01Z",
                      "b": [{"p": 99, "s": 3}], "a": []}
            live_stream.store_event(db, row, first)
            live_stream.store_event(db, row, first)
            live_stream.store_event(db, row, second)
            db.commit()
            rows = db.execute(
                "SELECT event_type, timestamp, raw_json FROM live_market_events ORDER BY timestamp"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "o")
            self.assertEqual(json.loads(rows[1][2])["b"][0]["s"], 3)

    def test_live_news_upserts_article_and_links_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            article = {"T": "n", "id": 42, "headline": "Original", "summary": "Summary",
                       "author": "Reporter", "created_at": "2026-01-01T00:00:00Z",
                       "updated_at": "2026-01-01T00:00:01Z", "content": "Body",
                       "url": "https://example.test/article", "symbols": ["AAPL", "MSFT"],
                       "source": "test"}
            live_stream.store_news(db, article)
            article.update(headline="Updated", updated_at="2026-01-01T00:00:02Z")
            live_stream.store_news(db, article)
            db.commit()
            self.assertEqual(db.execute("SELECT count(*) FROM news_articles").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT headline FROM news_articles").fetchone()[0], "Updated")
            self.assertEqual(db.execute("SELECT count(*) FROM news_article_symbols").fetchone()[0], 2)
            self.assertEqual(live_stream.news_symbol("btc/usd"), "BTCUSD")

    def test_ollama_structured_sentiment_is_validated_and_stored(self):
        result = {"label": "positive", "score": 0.7, "confidence": 0.8,
                  "impact_horizon": "short_term", "rationale": "Expected demand improves."}
        envelope = {"message": {"content": json.dumps(result)}, "total_duration": 123,
                    "prompt_eval_count": 20, "eval_count": 10}
        response = io.BytesIO(json.dumps(envelope).encode())
        with patch.object(news_sentiment, "urlopen", return_value=response) as request:
            parsed, raw = news_sentiment.ollama(
                "http://127.0.0.1:11434", "test-model", "Article", 5
            )
        self.assertEqual(parsed["score"], 0.7)
        sent_payload = json.loads(request.call_args.args[0].data)
        self.assertFalse(sent_payload["stream"])
        self.assertEqual(sent_payload["format"], news_sentiment.SCHEMA)
        self.assertEqual(sent_payload["options"]["temperature"], 0)
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            article = {"T": "n", "id": 99, "headline": "News", "summary": "Summary",
                       "created_at": "2026-01-01T00:00:00Z",
                       "updated_at": "2026-01-01T00:00:01Z", "symbols": ["AAPL"]}
            live_stream.store_news(db, article)
            news_sentiment.save(db, "99", "test-model", parsed, raw)
            db.commit()
            row = db.execute("SELECT label, score, confidence FROM news_sentiment").fetchone()
            self.assertEqual(row, ("positive", 0.7, 0.8))

    def test_sentiment_rejects_invalid_ranges_and_strips_html(self):
        with self.assertRaises(RuntimeError):
            news_sentiment.validate({"label": "positive", "score": 2, "confidence": 1,
                                     "impact_horizon": "short_term", "rationale": "x"})
        self.assertEqual(news_sentiment.plain_text("<p>Profit &amp; growth</p>"),
                         "Profit & growth")

    def test_stock_history_paginates_and_upserts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            args = self.history_args(path, "stock", "aapl")
            pages = [
                {"bars": [{"t": "2026-01-01T00:00:00Z", "o": 1, "h": 2, "l": 1,
                            "c": 2, "v": 10}], "next_page_token": "next"},
                {"bars": [{"t": "2026-01-02T00:00:00Z", "o": 2, "h": 3, "l": 2,
                            "c": 3, "v": 20}], "next_page_token": None},
            ]
            with patch.object(alpaca_store.Alpaca, "__init__", return_value=None), \
                 patch.object(alpaca_store.Alpaca, "get", side_effect=pages) as get:
                alpaca_store.history(args)
            db = alpaca_store.connect(path)
            self.assertEqual(db.execute("SELECT count(*) FROM bars").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT status FROM fetch_runs").fetchone()[0], "complete")
            self.assertEqual(args.symbol, "AAPL")
            self.assertIsNone(get.call_args_list[0].args[2]["page_token"])
            self.assertEqual(get.call_args_list[1].args[2]["page_token"], "next")

    def test_crypto_history_records_location_and_partial_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            args = self.history_args(path, "crypto", "btc/usd", location="eu-1", max_pages=1)
            payload = {"bars": {"BTC/USD": [
                {"t": "2026-01-01T00:00:00Z", "o": 1, "h": 2, "l": 1, "c": 2, "v": 10}
            ]}, "next_page_token": "more"}
            with patch.object(alpaca_store.Alpaca, "__init__", return_value=None), \
                 patch.object(alpaca_store.Alpaca, "get", return_value=payload):
                alpaca_store.history(args)
            db = alpaca_store.connect(path)
            self.assertEqual(db.execute("SELECT feed FROM bars").fetchone()[0], "eu-1")
            self.assertEqual(db.execute("SELECT status FROM fetch_runs").fetchone()[0], "partial")

    def test_repeated_history_page_token_fails_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            args = self.history_args(path, "stock", "AAPL")
            payload = {"bars": [], "next_page_token": "same"}
            with patch.object(alpaca_store.Alpaca, "__init__", return_value=None), \
                 patch.object(alpaca_store.Alpaca, "get", return_value=payload):
                with self.assertRaises(RuntimeError):
                    alpaca_store.history(args)
            db = alpaca_store.connect(path)
            self.assertEqual(db.execute("SELECT status FROM fetch_runs").fetchone()[0], "failed")

    def test_sec_sic_classification_is_stored_and_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            classify_symbols.save(db, "AAPL", code="3571", industry="Electronic Computers",
                                  company="Apple Inc.", cik="0000320193", source="test", status="classified")
            classify_symbols.save(db, "AAPL", code="3571", industry="Electronic Computers",
                                  company="Apple Inc.", cik="0000320193", source="test2", status="classified")
            db.commit()
            row = db.execute("""
                SELECT classification_code, industry, sector, source_url
                FROM symbol_classifications WHERE symbol='AAPL'
            """).fetchone()
            self.assertEqual(db.execute("SELECT count(*) FROM symbol_classifications").fetchone()[0], 1)
            self.assertEqual(row[0], "3571")
            self.assertEqual(row[1], "Electronic Computers")
            self.assertEqual(row[2], "Manufacturing")
            self.assertEqual(row[3], "test2")

    def test_sec_ticker_map_and_sector_ranges(self):
        payload = {"0": {"ticker": "aapl", "cik_str": 320193, "title": "Apple Inc."}}
        result = classify_symbols.ticker_map(payload)
        self.assertEqual(result["AAPL"]["cik_str"], 320193)
        self.assertEqual(classify_symbols.sic_sector("6021"),
                         "Finance, Insurance and Real Estate")
        self.assertIsNone(classify_symbols.sic_sector(None))

    def test_tickrs_industries_only_include_symbols_with_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db = alpaca_store.connect(Path(directory) / "test.sqlite3")
            args = argparse.Namespace(asset_class="stock", symbol="AAPL", timeframe="1Day",
                                      feed="iex", location="", adjustment="raw")
            bar = {"t": "2026-01-01T00:00:00Z", "o": 1, "h": 2, "l": 1,
                   "c": 2, "v": 10}
            alpaca_store.save_bars(db, args, [bar])
            classify_symbols.save(db, "AAPL", code="3571", industry="Electronic Computers",
                                  company="Apple", cik="1", source="test", status="classified")
            classify_symbols.save(db, "MSFT", code="7372", industry="Prepackaged Software",
                                  company="Microsoft", cik="2", source="test", status="classified")
            db.commit()
            self.assertEqual(tickrs_industry.industries(db),
                             [("Electronic Computers", ["AAPL"])])
            self.assertEqual(tickrs_industry.named(
                [("Electronic Computers", ["AAPL"])], "electronic computers"
            )[1], ["AAPL"])

    def test_stream_credentials_load_from_persistent_file(self):
        with tempfile.TemporaryDirectory() as directory:
            credential_file = Path(directory) / "alpaca.env"
            credential_file.write_text(
                'APCA_API_KEY_ID="test-key"\nAPCA_API_SECRET_KEY="test secret"\n',
                encoding="utf-8",
            )
            with patch.object(stream_service, "CREDENTIAL_FILE", credential_file), \
                 patch.dict(os.environ, {}, clear=True):
                self.assertEqual(stream_service.require_credentials(),
                                 ("test-key", "test secret"))

    def test_stream_unit_uses_embedded_finance_shell_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            systemd = root / "systemd"
            credential = root / "config" / "alpaca.env"
            with patch.object(stream_service, "USER_SYSTEMD", systemd), \
                 patch.object(stream_service, "CREDENTIAL_FILE", credential), \
                 patch.object(stream_service.subprocess, "run"):
                stream_service.install_runtime("test-key", "test-secret")
            unit = (systemd / stream_service.UNIT_NAME).read_text(encoding="utf-8")
            self.assertIn(str(stream_service.ROOT), unit)
            self.assertIn(str(stream_service.ROOT / "lib" / "live_stream.py"), unit)
            self.assertNotIn("/home/guyyatsu/Documents/finance-shell", unit)
            self.assertNotIn("@WORKING_DIRECTORY@", unit)


if __name__ == "__main__":
    unittest.main()
