"""Install and control the single watchlist-driven systemd user service."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from alpaca_store import DEFAULT_DB, connect, now
import stream_view

ROOT = Path(__file__).resolve().parents[1]
UNIT_NAME = "fsh-alpaca-stream.service"
LEGACY_UNIT_NAME = "fsh-alpaca-stream@.service"
USER_SYSTEMD = Path.home() / ".config" / "systemd" / "user"
CREDENTIAL_FILE = Path.home() / ".config" / "finance-shell" / "alpaca.env"


def file_credentials() -> tuple[str | None, str | None]:
    if not CREDENTIAL_FILE.is_file():
        return None, None
    values: dict[str, str] = {}
    for original in CREDENTIAL_FILE.read_text(encoding="utf-8").splitlines():
        line = original.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"):
            continue
        parsed = shlex.split(value, comments=True, posix=True)
        if len(parsed) != 1:
            raise SystemExit(f"invalid {name} assignment in {CREDENTIAL_FILE}")
        values[name] = parsed[0]
    return values.get("APCA_API_KEY_ID"), values.get("APCA_API_SECRET_KEY")


def require_credentials() -> tuple[str, str]:
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        key, secret = file_credentials()
    if not key or not secret:
        raise SystemExit(
            f"set APCA_API_KEY_ID and APCA_API_SECRET_KEY in the environment or {CREDENTIAL_FILE}"
        )
    return key, secret


def env_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "") + '"'


def newsdata_credential() -> str | None:
    configured = os.environ.get("NEWSDATA_API_KEY")
    if configured or not CREDENTIAL_FILE.is_file():
        return configured
    for original in CREDENTIAL_FILE.read_text(encoding="utf-8").splitlines():
        if original.strip().startswith("NEWSDATA_API_KEY="):
            parsed = shlex.split(original.split("=", 1)[1], comments=True, posix=True)
            return parsed[0] if len(parsed) == 1 else None
    return None


def install_runtime(key: str, secret: str, database: Path = DEFAULT_DB) -> None:
    USER_SYSTEMD.mkdir(parents=True, exist_ok=True)
    CREDENTIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    newsdata_key = newsdata_credential()
    optional_news = f"NEWSDATA_API_KEY={env_quote(newsdata_key)}\n" if newsdata_key else ""
    CREDENTIAL_FILE.write_text(
        f"APCA_API_KEY_ID={env_quote(key)}\nAPCA_API_SECRET_KEY={env_quote(secret)}\n"
        + optional_news,
        encoding="utf-8",
    )
    CREDENTIAL_FILE.chmod(0o600)
    source = ROOT / "systemd" / UNIT_NAME
    unit = source.read_text(encoding="utf-8")
    unit = unit.replace("@WORKING_DIRECTORY@", str(ROOT))
    unit = unit.replace("@PYTHON@", sys.executable)
    unit = unit.replace("@STREAM_SCRIPT@", str(ROOT / "lib" / "live_stream.py"))
    unit = unit.replace("@DATABASE@", str(database.expanduser().resolve()))
    (USER_SYSTEMD / UNIT_NAME).write_text(unit, encoding="utf-8")
    legacy = USER_SYSTEMD / LEGACY_UNIT_NAME
    if legacy.exists():
        legacy.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", "--user", *args], check=check, text=True)


def restart_if_running(database: Path = DEFAULT_DB) -> None:
    # Deliberately leave a stopped or not-yet-installed daemon stopped.
    active = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", UNIT_NAME], check=False
    ).returncode == 0
    if active:
        key, secret = require_credentials()
        install_runtime(key, secret, database)
        systemctl("restart", UNIT_NAME)


def options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("symbol")
    parser.add_argument("--class", dest="asset_class", choices=("stock", "crypto"), required=True)
    parser.add_argument("--feed", choices=("iex", "sip"))
    parser.add_argument("--location", choices=("us", "us-1", "eu-1"))


def add(args: argparse.Namespace) -> None:
    symbol = args.symbol.upper()
    feed = args.feed or ("iex" if args.asset_class == "stock" else "")
    location = args.location or ("us" if args.asset_class == "crypto" else "")
    db = connect(args.db)
    before = db.total_changes
    db.execute("""
        INSERT OR IGNORE INTO stream_watchlist(asset_class, symbol, feed, location, added_at)
        VALUES (?, ?, ?, ?, ?)
    """, (args.asset_class, symbol, feed, location, now()))
    changed = db.total_changes != before
    db.commit()
    db.close()
    print(f"{'Added' if changed else 'Already watching'} {args.asset_class} {symbol}")
    if changed:
        restart_if_running(args.db)


def remove(args: argparse.Namespace) -> None:
    symbol = args.symbol.upper()
    feed = args.feed or ("iex" if args.asset_class == "stock" else "")
    location = args.location or ("us" if args.asset_class == "crypto" else "")
    db = connect(args.db)
    cursor = db.execute("""
        DELETE FROM stream_watchlist
        WHERE asset_class=? AND symbol=? AND feed=? AND location=?
    """, (args.asset_class, symbol, feed, location))
    db.commit()
    db.close()
    if not cursor.rowcount:
        raise SystemExit(f"not on watchlist: {args.asset_class} {symbol}")
    print(f"Removed {args.asset_class} {symbol}")
    restart_if_running(args.db)


def watchlist(args: argparse.Namespace) -> None:
    db = connect(args.db)
    rows = db.execute("""
        SELECT asset_class, symbol, feed, location, added_at
        FROM stream_watchlist ORDER BY asset_class, symbol, feed, location
    """).fetchall()
    db.close()
    if not rows:
        print("Watchlist is empty")
        return
    print(f"{'CLASS':<8} {'SYMBOL':<16} {'FEED':<6} {'LOCATION':<8} ADDED")
    for row in rows:
        print(f"{row[0]:<8} {row[1]:<16} {row[2] or '-':<6} {row[3] or '-':<8} {row[4]}")


def start(args: argparse.Namespace) -> None:
    db = connect(args.db)
    count = db.execute("SELECT count(*) FROM stream_watchlist").fetchone()[0]
    db.close()
    if not count:
        raise SystemExit("watchlist is empty; add at least one symbol before starting")
    key, secret = require_credentials()
    install_runtime(key, secret, args.db)
    systemctl("enable", "--now", UNIT_NAME)
    print(f"Started {UNIT_NAME}")


def stop(_: argparse.Namespace) -> None:
    systemctl("disable", "--now", UNIT_NAME)
    print(f"Stopped {UNIT_NAME}")


def restart(args: argparse.Namespace) -> None:
    key, secret = require_credentials()
    install_runtime(key, secret, args.db)
    systemctl("restart", UNIT_NAME)
    print(f"Restarted {UNIT_NAME}")


def status(_: argparse.Namespace) -> None:
    systemctl("status", UNIT_NAME, "--no-pager", check=False)


def view(args: argparse.Namespace) -> None:
    stream_view.run(args)


def main() -> None:
    root = argparse.ArgumentParser(prog="fsh alpaca stream")
    root.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = root.add_subparsers(required=True)
    for name, run in (("add", add), ("remove", remove)):
        item = commands.add_parser(name)
        options(item)
        item.set_defaults(run=run)
    item = commands.add_parser("list", aliases=["watchlist"])
    item.set_defaults(run=watchlist)
    for name, run in (("start", start), ("stop", stop), ("restart", restart), ("status", status)):
        item = commands.add_parser(name)
        item.set_defaults(run=run)
    item = commands.add_parser("view", help="view incoming books and trades live")
    stream_view.add_arguments(item)
    item.set_defaults(run=view)
    args = root.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
