#!/usr/bin/env python3
"""Delete news older than the configured retention window."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import sqlite3


DEFAULT_DAYS = 7
DEFAULT_SQLITE = Path(os.environ.get(
    "ALPACA_DATA_DB",
    Path.home() / ".local/share/df-fintechterm/market-data/alpaca.sqlite3",
)).expanduser()


def cutoff(days: int, *, current_time: datetime | None = None) -> datetime:
    if days < 1:
        raise ValueError("retention days must be at least 1")
    moment = current_time or datetime.now(UTC)
    if moment.tzinfo is None:
        raise ValueError("current_time must be timezone-aware")
    return moment.astimezone(UTC) - timedelta(days=days)


def prune_sqlite(path: Path, before: datetime) -> int:
    """Prune the live feed if its database exists; never create an empty DB."""
    if not path.is_file():
        return 0
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='news_articles'"
        ).fetchone()
        if table is None:
            return 0
        cursor = db.execute(
            "DELETE FROM news_articles WHERE datetime(created_at) < datetime(?)",
            (before.isoformat(),),
        )
        db.commit()
        return cursor.rowcount
    finally:
        db.close()


def prune_postgres(database_url: str, before: datetime) -> int:
    import psycopg

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM news WHERE created_at < %s", (before,))
            deleted = cursor.rowcount
        connection.commit()
    return deleted


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--days", type=int, default=DEFAULT_DAYS)
    command.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    command.add_argument(
        "--postgres-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL URL; defaults to DATABASE_URL and is optional",
    )
    return command


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        before = cutoff(arguments.days)
    except ValueError as error:
        parser().error(str(error))
    sqlite_deleted = prune_sqlite(arguments.sqlite, before)
    postgres_deleted = 0
    if arguments.postgres_url:
        postgres_deleted = prune_postgres(arguments.postgres_url, before)
    print(
        f"News retention complete: SQLite={sqlite_deleted}, "
        f"PostgreSQL={postgres_deleted}, retained={arguments.days} days"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
