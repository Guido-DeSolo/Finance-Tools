import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "alerts"))

import alerting


def database():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE live_trades (
          symbol TEXT, price REAL, timestamp TEXT, received_at TEXT
        );
        CREATE TABLE technical_analysis_snapshots (
          symbol TEXT, indicators_json TEXT, updated_at TEXT
        );
    """)
    alerting.ensure_schema(db)
    return db


class AlertTests(unittest.TestCase):
    def test_cross_condition_requires_previous_observation(self):
        self.assertFalse(alerting.condition("crosses_above", 101, 100, None))
        self.assertTrue(alerting.condition("crosses_above", 101, 100, 99))
        self.assertFalse(alerting.condition("crosses_above", 102, 100, 101))

    def test_rule_queues_once_until_condition_rearms(self):
        db = database()
        rule_id = alerting.add_rule(db, "AAPL", "price", "gt", 100, 0, ["discord"])
        db.execute("INSERT INTO live_trades VALUES (?,?,?,?)", ("AAPL", 101, "2", "2"))
        self.assertEqual(alerting.queue_triggers(db), 1)
        self.assertEqual(alerting.queue_triggers(db), 0)
        db.execute("DELETE FROM live_trades")
        db.execute("INSERT INTO live_trades VALUES (?,?,?,?)", ("AAPL", 99, "3", "3"))
        self.assertEqual(alerting.queue_triggers(db), 0)
        db.execute("DELETE FROM live_trades")
        db.execute("INSERT INTO live_trades VALUES (?,?,?,?)", ("AAPL", 102, "4", "4"))
        self.assertEqual(alerting.queue_triggers(db), 1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM alert_deliveries WHERE rule_id=?", (rule_id,)).fetchone()[0], 2)
        db.close()

    def test_indicator_rule_reads_normalized_snapshot(self):
        db = database()
        db.execute("INSERT INTO technical_analysis_snapshots VALUES (?,?,?)",
                   ("MSFT", json.dumps({"rsi": 72.5}), "now"))
        self.assertEqual(alerting.metric_value(db, "MSFT", "rsi"), 72.5)
        db.close()

    def test_discord_bot_disables_mentions(self):
        response = MagicMock(status_code=200, text="")
        session = MagicMock(); session.post.return_value = response
        transport = alerting.BotTransports({
            "DISCORD_BOT_TOKEN": "token", "DISCORD_CHANNEL_ID": "channel",
        }, session)
        transport.send("discord", "@everyone test")
        call = session.post.call_args
        self.assertEqual(call.args[0], "https://discord.com/api/v10/channels/channel/messages")
        self.assertEqual(call.kwargs["json"]["allowed_mentions"], {"parse": []})
        self.assertEqual(call.kwargs["headers"]["Authorization"], "Bot token")

    def test_telegram_bot_uses_plain_send_message(self):
        response = MagicMock(status_code=200, text="", json=MagicMock(return_value={"ok": True}))
        session = MagicMock(); session.post.return_value = response
        transport = alerting.BotTransports({
            "TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat",
        }, session)
        transport.send("telegram", "test")
        call = session.post.call_args
        self.assertEqual(call.args[0], "https://api.telegram.org/bottoken/sendMessage")
        self.assertEqual(call.kwargs["json"], {"chat_id": "chat", "text": "test"})

    def test_failed_delivery_remains_retryable(self):
        db = database()
        rule_id = alerting.add_rule(db, "AAPL", "price", "gt", 100, 0, ["discord"])
        db.execute("INSERT INTO alert_deliveries(rule_id,destination,message,created_at) VALUES (?,?,?,?)",
                   (rule_id, "discord", "test", alerting.utc_now()))
        transport = MagicMock(); transport.send.side_effect = RuntimeError("offline")
        self.assertEqual(alerting.deliver_pending(db, transport), (0, 1))
        transport.send.side_effect = None
        self.assertEqual(alerting.deliver_pending(db, transport), (1, 0))
        self.assertEqual(db.execute("SELECT status,attempts FROM alert_deliveries").fetchone(), ("sent", 2))
        db.close()


if __name__ == "__main__":
    unittest.main()
