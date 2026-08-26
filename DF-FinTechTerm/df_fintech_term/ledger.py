from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from uuid import uuid4


class LedgerError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise LedgerError(f"invalid ledger payload: {error}") from error


def _digest(event: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Verification:
    valid: bool
    events: int
    errors: tuple[str, ...]


class Ledger:
    """Append-only, hash-chained SQLite activity journal."""

    def __init__(self, path: Path, mode: str):
        self.path = Path(path)
        self.mode = mode

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS ledger_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                mode TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
            BEFORE UPDATE ON ledger_events BEGIN
                SELECT RAISE(ABORT, 'ledger events are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
            BEFORE DELETE ON ledger_events BEGIN
                SELECT RAISE(ABORT, 'ledger events are append-only');
            END;
        """)
        return connection

    def record(self, category: str, action: str, payload: dict[str, Any]) -> str:
        payload_json = _canonical(payload)
        event_id = str(uuid4())
        recorded_at = datetime.now(UTC).isoformat()
        connection = None
        try:
            connection = self._connect()
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT event_hash FROM ledger_events ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous_hash = row["event_hash"] if row else None
                core = {
                    "event_id": event_id, "recorded_at": recorded_at,
                    "category": category, "action": action, "mode": self.mode,
                    "payload_json": payload_json, "previous_hash": previous_hash,
                }
                event_hash = _digest(core)
                connection.execute(
                    """INSERT INTO ledger_events
                       (event_id, recorded_at, category, action, mode, payload_json,
                        previous_hash, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*core.values(), event_hash),
                )
            return event_id
        except sqlite3.Error as error:
            raise LedgerError(f"could not append ledger event: {error}") from error
        finally:
            if connection is not None:
                connection.close()

    def rows(self) -> Iterable[sqlite3.Row]:
        if not self.path.exists():
            return ()
        connection = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return tuple(connection.execute("SELECT * FROM ledger_events ORDER BY sequence"))
        finally:
            connection.close()

    def verify(self) -> Verification:
        if not self.path.exists():
            return Verification(False, 0, ("ledger database does not exist",))
        errors: list[str] = []
        previous_hash = None
        rows = tuple(self.rows())
        for expected, row in enumerate(rows, 1):
            if row["sequence"] != expected:
                errors.append(f"sequence {row['sequence']}: expected {expected}")
            if row["previous_hash"] != previous_hash:
                errors.append(f"sequence {row['sequence']}: previous hash mismatch")
            core = {key: row[key] for key in (
                "event_id", "recorded_at", "category", "action", "mode",
                "payload_json", "previous_hash",
            )}
            if _digest(core) != row["event_hash"]:
                errors.append(f"sequence {row['sequence']}: event hash mismatch")
            try:
                json.loads(row["payload_json"])
            except json.JSONDecodeError:
                errors.append(f"sequence {row['sequence']}: invalid payload JSON")
            previous_hash = row["event_hash"]
        return Verification(not errors, len(rows), tuple(errors))

    def export_jsonl(self, output: Path) -> int:
        rows = tuple(self.rows())
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as stream:
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                stream.write(_canonical(item) + "\n")
        return len(rows)
