"""Finance Shell command catalog and safe argument construction for the TUI."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FinanceTool:
    key: str
    title: str
    command: tuple[str, ...]
    arguments: str | None = None


FINANCE_TOOLS = (
    FinanceTool("indicators-test", "Indicators · run tests", ("indicators", "test")),
    FinanceTool("indicators-report", "Indicators · validation report", ("indicators", "report")),
    FinanceTool("indicators-example", "Indicators · example data", ("indicators", "example")),
    FinanceTool("price-bitcoin", "Price · Bitcoin", ("price", "bitcoin")),
    FinanceTool("price-silver", "Price · silver", ("price", "silver")),
    FinanceTool("tickrs", "Viewer · Tickrs", ("tickrs",), "optional Tickrs arguments"),
    FinanceTool("ticker", "Viewer · Ticker", ("ticker",), "optional Ticker arguments"),
    FinanceTool("tickrs-industry", "Viewer · Tickrs by industry", ("tickrs-industry",), "optional: --industry NAME"),
    FinanceTool("classify-refresh", "Classification · refresh SEC SIC", ("classify", "refresh"), "optional symbols and flags"),
    FinanceTool("classify-list", "Classification · list", ("classify", "list"), "optional flags"),
    FinanceTool("alpaca-sync-assets", "Alpaca · sync asset catalogs", ("alpaca", "sync-assets"), "optional flags"),
    FinanceTool("alpaca-history", "Alpaca · download history", ("alpaca", "history"), "SYMBOL --class stock|crypto and optional flags"),
    FinanceTool("alpaca-history-list", "Alpaca · history from symbol file", ("alpaca", "history-list"), "FILE and optional flags"),
    FinanceTool("alpaca-status", "Alpaca · database status", ("alpaca", "status"), "optional flags"),
    FinanceTool("alpaca-news", "Alpaca · stored news", ("alpaca", "news"), "optional SYMBOL and flags"),
    FinanceTool("alpaca-analysis", "Alpaca · live technical analysis", ("alpaca", "analysis"), "optional SYMBOL and flags"),
    FinanceTool("alpaca-timeframes", "Alpaca · supported timeframes", ("alpaca", "timeframes")),
    FinanceTool("stream-add", "Stream · add watch symbol", ("alpaca", "stream", "add"), "SYMBOL --class stock|crypto and optional flags"),
    FinanceTool("stream-remove", "Stream · remove watch symbol", ("alpaca", "stream", "remove"), "SYMBOL --class stock|crypto and optional flags"),
    FinanceTool("stream-list", "Stream · list watchlist", ("alpaca", "stream", "list"), "optional flags"),
    FinanceTool("stream-start", "Stream · start daemon", ("alpaca", "stream", "start"), "optional flags"),
    FinanceTool("stream-stop", "Stream · stop daemon", ("alpaca", "stream", "stop"), "optional flags"),
    FinanceTool("stream-restart", "Stream · restart daemon", ("alpaca", "stream", "restart"), "optional flags"),
    FinanceTool("stream-status", "Stream · daemon status", ("alpaca", "stream", "status"), "optional flags"),
    FinanceTool("stream-view", "Stream · live market view", ("alpaca", "stream", "view"), "optional SYMBOL and flags"),
    FinanceTool("services", "Services · background catalog", ("services",)),
    FinanceTool("service-run", "Services · run worker", ("service",), "SERVICE and optional arguments"),
    FinanceTool("actions", "Actions · research catalog", ("actions",)),
    FinanceTool("action-run", "Actions · run research", ("action",), "ACTION and optional arguments"),
    FinanceTool("calc-compound", "Calculator · compound growth", ("calc", "compound"), "PRINCIPAL RATE YEARS [CONTRIBUTION]"),
    FinanceTool("calc-gain", "Calculator · gain/loss", ("calc", "gain"), "COST VALUE"),
    FinanceTool("calc-budget", "Calculator · budget", ("calc", "budget"), "INCOME EXPENSE..."),
    FinanceTool("calc-allocate", "Calculator · allocate", ("calc", "allocate"), "TOTAL WEIGHT..."),
    FinanceTool("doctor", "System · doctor", ("doctor",)),
    FinanceTool("help", "System · Finance Shell help", ("help",)),
)


def default_finance_shell() -> Path:
    configured = os.environ.get("FINANCE_SHELL")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "finance-shell" / "fsh"


def build_command(fsh: Path, tool: FinanceTool, arguments: str = "") -> list[str]:
    """Build an argv list without invoking a shell or interpreting metacharacters."""
    return [str(fsh), *tool.command, *shlex.split(arguments)]


def catalog_keys() -> set[str]:
    return {tool.key for tool in FINANCE_TOOLS}
