#!/usr/bin/env python3
"""Explicit command boundary between DF-FinTechTerm services and user actions."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

from fintech_core import RuntimeConfig


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Operation:
    name: str
    script: str
    description: str
    writes_database: bool = False


SERVICES = {
    item.name: item for item in (
        Operation("market-minute", "data/ingest.py", "Ingest Alpaca one-minute IEX bars", True),
        Operation("market-daily-iex", "data/daily_ingest.py", "Ingest daily IEX bars", True),
        Operation("market-daily-sip", "data/daily_ingest_sip.py", "Ingest daily SIP bars", True),
        Operation("news-ingest", "data/news_ingest.py", "Ingest Alpaca news articles", True),
        Operation("news-retention", "data/news_retention.py", "Prune news older than seven days", True),
        Operation("alert-scan", "alerts/alerting.py", "Evaluate rules and deliver bot alerts", True),
        Operation("insider-ingest", "data/insider.py", "Ingest normalized Form 4 activity", True),
        Operation("watchlist-refresh", "data/watchlist.py", "Refresh deterministic watchlist scores", True),
    )
}

ACTIONS = {
    item.name: item for item in (
        Operation("candidate-packets", "data/candidate_packet.py", "Build validated research packets"),
        Operation("daily-research", "research/daily_research.py", "Publish local-LLM daily research notebook"),
        Operation("alert-manage", "alerts/alerting.py", "Manage and test Discord/Telegram alerts", True),
        Operation("insider-backtest", "data/insider_backtest.py", "Run the insider-event study"),
        Operation("benchmark-quant-v2", "evaluation/quant_signal_benchmark.py", "Run deterministic QUANT benchmark"),
        Operation("portfolio-replay", "evaluation/portfolio_replay.py", "Replay explicit trade plans with costs"),
        Operation("execution-analysis", "evaluation/execution_analysis.py", "Import fills and assess execution quality", True),
        Operation("ledger-audit", "audit/ledger_cli.py", "Verify or export the activity ledger"),
    )
}


def catalog_payload() -> dict[str, object]:
    runtime = RuntimeConfig.from_env()
    return {
        "execution_mode": runtime.mode.value,
        "services": [asdict(item) for item in SERVICES.values()],
        "actions": [asdict(item) for item in ACTIONS.values()],
    }


def print_catalog(operations: dict[str, Operation], heading: str) -> None:
    print(heading)
    for operation in operations.values():
        marker = "database writer" if operation.writes_database else "read/research"
        print(f"  {operation.name:<22} {marker:<15} {operation.description}")


def run(operation: Operation, arguments: list[str]) -> int:
    script = ROOT / operation.script
    environment = dict(os.environ)
    paths = [str(ROOT / "data"), str(ROOT.parent)]
    if environment.get("PYTHONPATH"):
        paths.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    return result.returncode


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        prog="df-fintechterm",
        description="DF-FinTechTerm backend: services are scheduled workers; actions are user-requested jobs.",
    )
    subcommands = command.add_subparsers(dest="kind", required=True)
    subcommands.add_parser("services", help="List background/scheduled services")
    subcommands.add_parser("actions", help="List finite user actions")
    subcommands.add_parser("catalog", help="Print the machine-readable catalog")
    for kind, operations in (("service", SERVICES), ("action", ACTIONS)):
        child = subcommands.add_parser(kind, help=f"Run one {kind}")
        child.add_argument("name", choices=tuple(operations))
        child.add_argument("arguments", nargs=argparse.REMAINDER)
    return command


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.kind == "services":
        print_catalog(SERVICES, "BACKGROUND / SCHEDULED SERVICES")
        return 0
    if arguments.kind == "actions":
        print_catalog(ACTIONS, "USER ACTIONS")
        return 0
    if arguments.kind == "catalog":
        print(json.dumps(catalog_payload(), indent=2, sort_keys=True))
        return 0
    operations = SERVICES if arguments.kind == "service" else ACTIONS
    forwarded = arguments.arguments
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    return run(operations[arguments.name], forwarded)


if __name__ == "__main__":
    raise SystemExit(main())
