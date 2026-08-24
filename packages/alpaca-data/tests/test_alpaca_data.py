from __future__ import annotations

import argparse
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alpaca_data import store as alpaca_store
from alpaca_data import stream as live_stream
from alpaca_data import classification as classify_symbols
from alpaca_data import industry as tickrs_industry
from alpaca_data import sentiment as news_sentiment
from alpaca_data import MarketDataClient


class AlpacaStoreTests(unittest.TestCase):
    def test_importable_market_data_convenience_methods(self):
        client = MarketDataClient("key", "secret")
        responses = [
            {"snapshots": {"AAPL": {"latestTrade": {"p": 100}}}},
            {"quotes": {"AAPL": {"ap": 101}}},
            {"trades": {"AAPL": {"p": 100}}},
            {"snapshots": {"BTC/USD": {"latestTrade": {"p": 60000}}}},
            {"orderbooks": {"BTC/USD": {"b": [], "a": []}}},
        ]
        with patch.object(client, "get", side_effect=responses) as get:
            self.assertIn("AAPL", client.stock_snapshots(["aapl"]))
            self.assertIn("AAPL", client.latest_stock_quotes(["aapl"]))
            self.assertIn("AAPL", client.latest_stock_trades(["aapl"]))
            self.assertIn("BTC/USD", client.crypto_snapshots(["btc/usd"]))
            self.assertIn("BTC/USD", client.crypto_orderbooks(["btc/usd"]))
        self.assertEqual(get.call_args_list[0].args[2]["symbols"], "AAPL")
        self.assertEqual(get.call_args_list[-1].args[1],
                         "/v1beta3/crypto/us/latest/orderbooks")

    def test_market_data_client_requires_a_complete_credential_pair(self):
        with self.assertRaises(ValueError):
            MarketDataClient("key", None)

    def test_importable_historical_bars_paginate(self):
        client = MarketDataClient("key", "secret")
        pages = [
            {"bars": [{"t": "2026-01-01T00:00:00Z"}], "next_page_token": "two"},
            {"bars": [{"t": "2026-01-02T00:00:00Z"}], "next_page_token": None},
        ]
        with patch.object(client, "get", side_effect=pages) as get:
            bars = client.historical_bars("aapl", start="2026-01-01")
        self.assertEqual(len(bars), 2)
        self.assertEqual(get.call_args_list[0].args[1], "/v2/stocks/AAPL/bars")
        self.assertEqual(get.call_args_list[1].args[2]["page_token"], "two")

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

if __name__ == "__main__":
    unittest.main()
