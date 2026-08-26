"""DF-FinTechTerm command catalog and safe argument construction for the TUI."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolCommand:
    key: str
    title: str
    command: tuple[str, ...]
    arguments: str | None = None


TOOL_COMMANDS = (
    ToolCommand("indicators-test", "Indicators · run tests", ("indicators", "test")),
    ToolCommand("indicators-report", "Indicators · validation report", ("indicators", "report")),
    ToolCommand("indicators-example", "Indicators · example data", ("indicators", "example")),
    ToolCommand("price-bitcoin", "Price · Bitcoin", ("price", "bitcoin")),
    ToolCommand("price-silver", "Price · silver", ("price", "silver")),
    ToolCommand("tickrs", "Viewer · Tickrs", ("tickrs",), "optional Tickrs arguments"),
    ToolCommand("ticker", "Viewer · Ticker", ("ticker",), "optional Ticker arguments"),
    ToolCommand("tickrs-industry", "Viewer · Tickrs by industry", ("tickrs-industry",), "optional: --industry NAME"),
    ToolCommand("classify-refresh", "Classification · refresh SEC SIC", ("classify", "refresh"), "optional symbols and flags"),
    ToolCommand("classify-populate-alpaca", "Classification · populate all Alpaca industries", ("classify", "populate-alpaca"), "optional: --force"),
    ToolCommand("classify-list", "Classification · list", ("classify", "list"), "optional flags"),
    ToolCommand("sentiment-analyze", "News · analyze sentiment", ("sentiment", "analyze"), "ARTICLE_ID and optional flags"),
    ToolCommand("sentiment-pending", "News · analyze pending sentiment", ("sentiment", "pending"), "optional flags"),
    ToolCommand("sentiment-list", "News · list sentiment", ("sentiment", "list"), "optional SYMBOL and flags"),
    ToolCommand("alpaca-sync-assets", "Alpaca · sync asset catalogs", ("alpaca", "sync-assets"), "optional flags"),
    ToolCommand("alpaca-history", "Alpaca · download history", ("alpaca", "history"), "SYMBOL --class stock|crypto and optional flags"),
    ToolCommand("alpaca-update-history", "Alpaca · update every historical series", ("alpaca", "update-history"), "optional flags"),
    ToolCommand("alpaca-history-list", "Alpaca · history from symbol file", ("alpaca", "history-list"), "FILE and optional flags"),
    ToolCommand("alpaca-status", "Alpaca · database status", ("alpaca", "status"), "optional flags"),
    ToolCommand("alpaca-news", "Alpaca · stored news", ("alpaca", "news"), "optional SYMBOL and flags"),
    ToolCommand("alpaca-analysis", "Alpaca · live technical analysis", ("alpaca", "analysis"), "optional SYMBOL and flags"),
    ToolCommand("alpaca-timeframes", "Alpaca · supported timeframes", ("alpaca", "timeframes")),
    ToolCommand("stream-add", "Stream · add watch symbol", ("alpaca", "stream", "add"), "SYMBOL --class stock|crypto and optional flags"),
    ToolCommand("stream-remove", "Stream · remove watch symbol", ("alpaca", "stream", "remove"), "SYMBOL --class stock|crypto and optional flags"),
    ToolCommand("stream-list", "Stream · list watchlist", ("alpaca", "stream", "list"), "optional flags"),
    ToolCommand("stream-start", "Stream · start daemon", ("alpaca", "stream", "start"), "optional flags"),
    ToolCommand("stream-stop", "Stream · stop daemon", ("alpaca", "stream", "stop"), "optional flags"),
    ToolCommand("stream-restart", "Stream · restart daemon", ("alpaca", "stream", "restart"), "optional flags"),
    ToolCommand("stream-status", "Stream · daemon status", ("alpaca", "stream", "status"), "optional flags"),
    ToolCommand("stream-view", "Stream · live market view", ("alpaca", "stream", "view"), "optional SYMBOL and flags"),
    ToolCommand("services", "Services · background catalog", ("services",)),
    ToolCommand("service-run", "Services · run worker", ("service",), "SERVICE and optional arguments"),
    ToolCommand("actions", "Actions · research catalog", ("actions",)),
    ToolCommand("action-run", "Actions · run research", ("action",), "ACTION and optional arguments"),
    ToolCommand("calc-compound", "Calculator · compound growth", ("calc", "compound"), "PRINCIPAL RATE YEARS [CONTRIBUTION]"),
    ToolCommand("calc-gain", "Calculator · gain/loss", ("calc", "gain"), "COST VALUE"),
    ToolCommand("calc-budget", "Calculator · budget", ("calc", "budget"), "INCOME EXPENSE..."),
    ToolCommand("calc-allocate", "Calculator · allocate", ("calc", "allocate"), "TOTAL WEIGHT..."),
    ToolCommand("doctor", "System · doctor", ("doctor",)),
    ToolCommand("help", "System · DF-FinTechTerm help", ("help",)),
)


def default_launcher() -> Path:
    configured = os.environ.get("DF_FINTECHTERM_LAUNCHER")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[1] / "df-fintechterm"


def build_command(launcher: Path, tool: ToolCommand, arguments: str = "") -> list[str]:
    """Build an argv list without invoking a shell or interpreting metacharacters."""
    return [str(launcher), *tool.command, *shlex.split(arguments)]


def catalog_keys() -> set[str]:
    return {tool.key for tool in TOOL_COMMANDS}
