#!/usr/bin/env python3
"""Deterministic SQLite alert rules with Discord and Telegram bot delivery."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

METRICS = {"price", "rsi", "adx", "macd", "macd_signal", "macd_histogram", "stochastic_k", "stochastic_d"}
OPERATORS = {"gt", "gte", "lt", "lte", "crosses_above", "crosses_below"}
DESTINATIONS = {"discord", "telegram"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            rule_id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, metric TEXT NOT NULL,
            operator TEXT NOT NULL, threshold REAL NOT NULL,
            cooldown_seconds INTEGER NOT NULL DEFAULT 900,
            destinations_json TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alert_rule_state (
            rule_id INTEGER PRIMARY KEY REFERENCES alert_rules(rule_id) ON DELETE CASCADE,
            last_value REAL, active INTEGER NOT NULL DEFAULT 0,
            last_triggered_at TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alert_deliveries (
            delivery_id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL,
            destination TEXT NOT NULL, message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, last_attempt_at TEXT, error TEXT,
            FOREIGN KEY(rule_id) REFERENCES alert_rules(rule_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS alert_deliveries_pending
            ON alert_deliveries(status, delivery_id);
    """)


def add_rule(db: sqlite3.Connection, symbol: str, metric: str, operator: str,
             threshold: float, cooldown: int, destinations: list[str]) -> int:
    metric, operator = metric.lower(), operator.lower()
    destinations = list(dict.fromkeys(item.lower() for item in destinations))
    if metric not in METRICS or operator not in OPERATORS:
        raise ValueError("unsupported alert metric or operator")
    if not destinations or not set(destinations) <= DESTINATIONS:
        raise ValueError("destinations must contain discord and/or telegram")
    if cooldown < 0:
        raise ValueError("cooldown must be nonnegative")
    cursor = db.execute("""
        INSERT INTO alert_rules
          (symbol, metric, operator, threshold, cooldown_seconds,
           destinations_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (symbol.upper(), metric, operator, threshold, cooldown,
          json.dumps(destinations), utc_now()))
    db.commit()
    return int(cursor.lastrowid)


def condition(operator: str, value: float, threshold: float, previous: float | None) -> bool:
    if operator == "gt": return value > threshold
    if operator == "gte": return value >= threshold
    if operator == "lt": return value < threshold
    if operator == "lte": return value <= threshold
    if operator == "crosses_above": return previous is not None and previous <= threshold < value
    if operator == "crosses_below": return previous is not None and previous >= threshold > value
    raise ValueError(f"unsupported operator: {operator}")


def metric_value(db: sqlite3.Connection, symbol: str, metric: str) -> float | None:
    if metric == "price":
        row = db.execute("""
            SELECT price FROM live_trades WHERE symbol=?
            ORDER BY timestamp DESC, received_at DESC LIMIT 1
        """, (symbol,)).fetchone()
        return float(row[0]) if row else None
    row = db.execute("""
        SELECT indicators_json FROM technical_analysis_snapshots
        WHERE symbol=? ORDER BY updated_at DESC LIMIT 1
    """, (symbol,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row[0]).get(metric)
        return float(value) if value is not None else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


class BotTransports:
    def __init__(self, environment: dict[str, str] | None = None,
                 session: requests.Session | None = None):
        self.environment = environment or dict(os.environ)
        self.session = session or requests.Session()

    def send(self, destination: str, message: str) -> None:
        if destination == "discord":
            self._discord(message)
        elif destination == "telegram":
            self._telegram(message)
        else:
            raise ValueError(f"unknown destination: {destination}")

    def _discord(self, message: str) -> None:
        token = self.environment.get("DISCORD_BOT_TOKEN")
        channel = self.environment.get("DISCORD_CHANNEL_ID")
        if not token or not channel:
            raise RuntimeError("Discord bot credentials are not configured")
        try:
            response = self.session.post(
                f"https://discord.com/api/v10/channels/{channel}/messages",
                headers={"Authorization": f"Bot {token}", "User-Agent": "DF-FinTechTerm/1"},
                json={"content": message[:2000], "allowed_mentions": {"parse": []}}, timeout=12,
            )
        except requests.RequestException as error:
            raise RuntimeError("Discord network error") from error
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Discord HTTP {response.status_code}: {response.text[:200]}")

    def _telegram(self, message: str) -> None:
        token = self.environment.get("TELEGRAM_BOT_TOKEN")
        chat = self.environment.get("TELEGRAM_CHAT_ID")
        if not token or not chat:
            raise RuntimeError("Telegram bot credentials are not configured")
        try:
            response = self.session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": message[:4096]}, timeout=12,
            )
        except requests.RequestException as error:
            raise RuntimeError("Telegram network error") from error
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code != 200 or not payload.get("ok"):
            raise RuntimeError(f"Telegram HTTP {response.status_code}: {payload.get('description', response.text[:200])}")


def queue_triggers(db: sqlite3.Connection) -> int:
    ensure_schema(db)
    queued = 0
    now = datetime.now(UTC)
    rules = db.execute("""
        SELECT rule.rule_id, rule.symbol, rule.metric, rule.operator, rule.threshold,
               rule.cooldown_seconds, rule.destinations_json, state.last_value,
               state.active, state.last_triggered_at
        FROM alert_rules AS rule LEFT JOIN alert_rule_state AS state USING(rule_id)
        WHERE rule.enabled=1 ORDER BY rule.rule_id
    """).fetchall()
    for rule_id, symbol, metric, operator, threshold, cooldown, encoded, previous, active, last_at in rules:
        value = metric_value(db, symbol, metric)
        if value is None:
            continue
        matched = condition(operator, value, threshold, previous)
        cooled = True
        if last_at:
            last = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
            cooled = (now - last).total_seconds() >= cooldown
        should_queue = matched and cooled and (not active or operator.startswith("crosses_"))
        if should_queue:
            message = f"DF-FinTechTerm alert: {symbol} {metric} {operator} {threshold:g} · observed {value:g}"
            for destination in json.loads(encoded):
                db.execute("""
                    INSERT INTO alert_deliveries
                      (rule_id, destination, message, created_at) VALUES (?, ?, ?, ?)
                """, (rule_id, destination, message, utc_now()))
                queued += 1
        db.execute("""
            INSERT INTO alert_rule_state(rule_id, last_value, active, last_triggered_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
              last_value=excluded.last_value, active=excluded.active,
              last_triggered_at=COALESCE(excluded.last_triggered_at, alert_rule_state.last_triggered_at),
              updated_at=excluded.updated_at
        """, (rule_id, value, int(matched), utc_now() if should_queue else None, utc_now()))
    db.commit()
    return queued


def deliver_pending(db: sqlite3.Connection, transports: BotTransports) -> tuple[int, int]:
    ensure_schema(db)
    sent = failed = 0
    rows = db.execute("""
        SELECT delivery_id, destination, message FROM alert_deliveries
        WHERE status IN ('pending', 'failed') AND attempts < 10
        ORDER BY delivery_id LIMIT 100
    """).fetchall()
    for delivery_id, destination, message in rows:
        try:
            transports.send(destination, message)
            db.execute("""
                UPDATE alert_deliveries SET status='sent', attempts=attempts+1,
                  last_attempt_at=?, error=NULL WHERE delivery_id=?
            """, (utc_now(), delivery_id))
            sent += 1
        except Exception as error:
            db.execute("""
                UPDATE alert_deliveries SET status='failed', attempts=attempts+1,
                  last_attempt_at=?, error=? WHERE delivery_id=?
            """, (utc_now(), str(error)[:300], delivery_id))
            failed += 1
    db.commit()
    return sent, failed


def default_database() -> Path:
    configured = os.environ.get("ALPACA_DATA_DB")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1] / "finance-shell/data/alpaca.sqlite3"


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage and deliver DF-FinTechTerm bot alerts.")
    parser.add_argument("--db", type=Path, default=default_database())
    commands = parser.add_subparsers(dest="command")
    add = commands.add_parser("add")
    add.add_argument("symbol"); add.add_argument("metric", choices=sorted(METRICS))
    add.add_argument("operator", choices=sorted(OPERATORS)); add.add_argument("threshold", type=float)
    add.add_argument("--cooldown", type=int, default=900)
    add.add_argument("--to", action="append", choices=sorted(DESTINATIONS), required=True)
    commands.add_parser("list")
    remove = commands.add_parser("remove"); remove.add_argument("rule_id", type=int)
    commands.add_parser("scan")
    test = commands.add_parser("test"); test.add_argument("--to", choices=sorted(DESTINATIONS), required=True)
    args = parser.parse_args()
    command = args.command or "scan"
    args.db.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(args.db)
    db.execute("PRAGMA foreign_keys=ON")
    ensure_schema(db)
    if command == "add":
        print(f"Added alert rule {add_rule(db, args.symbol, args.metric, args.operator, args.threshold, args.cooldown, args.to)}")
    elif command == "list":
        for row in db.execute("SELECT rule_id,symbol,metric,operator,threshold,cooldown_seconds,destinations_json,enabled FROM alert_rules ORDER BY rule_id"):
            print("\t".join(map(str, row)))
    elif command == "remove":
        db.execute("DELETE FROM alert_rules WHERE rule_id=?", (args.rule_id,)); db.commit()
        print(f"Removed alert rule {args.rule_id}")
    elif command == "test":
        BotTransports().send(args.to, "DF-FinTechTerm test alert")
        print(f"Sent test alert to {args.to}")
    else:
        queued = queue_triggers(db)
        sent, failed = deliver_pending(db, BotTransports())
        print(f"Alert scan: queued={queued} sent={sent} failed={failed}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
