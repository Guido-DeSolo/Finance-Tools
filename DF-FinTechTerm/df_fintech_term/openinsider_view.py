"""Fetch and cache the documented transactions on OpenInsider's homepage."""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.parse import urljoin

import requests


HOMEPAGE = "http://openinsider.com/"
CACHE_SECONDS = 300


class _HomepageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.heading = ""
        self._heading_tag = ""
        self._heading_text: list[str] = []
        self._in_table = False
        self._in_body = False
        self._in_cell = False
        self._cell_text: list[str] = []
        self._cell_link = ""
        self._row: list[tuple[str, str]] = []
        self.trades: list[dict[str, Any]] = []

    @staticmethod
    def _attrs(attributes: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key: value or "" for key, value in attributes}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = self._attrs(attrs)
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_text = []
        elif tag == "table" and "tinytable" in attributes.get("class", "").split():
            self._in_table = True
        elif self._in_table and tag == "tbody":
            self._in_body = True
        elif self._in_body and tag == "tr":
            self._row = []
        elif self._in_body and tag == "td":
            self._in_cell = True
            self._cell_text = []
            self._cell_link = ""
        elif self._in_cell and tag == "a" and not self._cell_link:
            self._cell_link = attributes.get("href", "")

    def handle_data(self, data: str) -> None:
        if self._heading_tag:
            self._heading_text.append(data)
        if self._in_cell:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == self._heading_tag:
            self.heading = _text(self._heading_text)
            self._heading_tag = ""
        elif tag == "td" and self._in_cell:
            self._row.append((_text(self._cell_text), self._cell_link))
            self._in_cell = False
        elif tag == "tr" and self._in_body and self._row:
            trade = _trade(self.heading, self._row)
            if trade:
                self.trades.append(trade)
            self._row = []
        elif tag == "tbody" and self._in_body:
            self._in_body = False
        elif tag == "table" and self._in_table:
            self._in_table = False


def _text(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _trade(section: str, cells: list[tuple[str, str]]) -> dict[str, Any] | None:
    if len(cells) < 13:
        return None
    values = [item[0] for item in cells]
    cluster = section == "Latest Cluster Buys"
    return {
        "section": section,
        "filing_date": values[1],
        "trade_date": values[2],
        "ticker": values[3],
        "company": values[4],
        "insider": f"{values[6]} insiders" if cluster else values[5],
        "title": values[5] if cluster else values[6],
        "trade_type": values[7],
        "price": values[8],
        "quantity": values[9],
        "owned": values[10],
        "ownership_change": values[11],
        "value": values[12],
        "filing_url": urljoin(HOMEPAGE, cells[1][1]),
    }


def parse_homepage(document: str) -> list[dict[str, Any]]:
    parser = _HomepageParser()
    parser.feed(document)
    return parser.trades


def fetch_homepage(get: Callable[..., Any] = requests.get) -> dict[str, Any]:
    response = get(
        HOMEPAGE,
        headers={"User-Agent": "DF-FinTechTerm/1.0 (personal research terminal)"},
        timeout=20,
    )
    response.raise_for_status()
    trades = parse_homepage(response.text)
    if not trades:
        raise ValueError("OpenInsider homepage contained no recognized trade rows")
    return {
        "source": HOMEPAGE,
        "fetched_at": datetime.now(UTC).isoformat(),
        "trades": trades,
    }


def _write_cache(cache: Path, payload: dict[str, Any]) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix(cache.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(cache)


def load_homepage(cache: Path, max_age: int = CACHE_SECONDS) -> dict[str, Any]:
    cached: dict[str, Any] = {}
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if not isinstance(cached, dict):
            raise ValueError("cache root is not an object")
        if time.time() - cache.stat().st_mtime < max_age:
            return cached
    except (OSError, ValueError, TypeError):
        cached = {}
    try:
        result = fetch_homepage()
        _write_cache(cache, result)
        return result
    except (requests.RequestException, OSError, ValueError) as error:
        if cached:
            fallback = {**cached, "stale": True, "error": str(error)}
        else:
            fallback = {"source": HOMEPAGE, "trades": [], "error": str(error)}
        try:
            _write_cache(cache, fallback)
        except OSError:
            pass
        return fallback
