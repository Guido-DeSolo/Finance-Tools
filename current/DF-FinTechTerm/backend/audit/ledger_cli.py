#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from df_fintech_term.ledger import Ledger


def default_path() -> Path:
    configured = os.environ.get("DF_LEDGER_DB")
    return (Path(configured).expanduser() if configured else
            Path.home() / ".local/share/df-fintechterm/ledger.sqlite3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify or export the activity ledger")
    parser.add_argument("--database", type=Path, default=default_path())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    export = commands.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    ledger = Ledger(args.database, "audit")
    if args.command == "verify":
        result = ledger.verify()
        print(json.dumps({"valid": result.valid, "events": result.events,
                          "errors": result.errors}, indent=2))
        return 0 if result.valid else 1
    count = ledger.export_jsonl(args.output)
    print(f"Exported {count} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
