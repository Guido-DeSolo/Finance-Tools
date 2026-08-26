"""Import-friendly Alpaca market-data REST client."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

from .tools.alpaca_store import Alpaca, DATA_URL, TRADING_URL


class MarketDataClient(Alpaca):
    """Read-only access to Alpaca market data and the asset catalog.

    Credentials may be passed explicitly or read from ``APCA_API_KEY_ID`` and
    ``APCA_API_SECRET_KEY``. The generic :meth:`get` method remains available
    for Alpaca endpoints not covered by a convenience method.
    """

    def __init__(self, key_id: str | None = None, secret_key: str | None = None) -> None:
        super().__init__(key_id, secret_key)

    @classmethod
    def from_environment(cls) -> "MarketDataClient":
        return cls(os.environ.get("APCA_API_KEY_ID"), os.environ.get("APCA_API_SECRET_KEY"))

    def assets(self, asset_class: str = "us_equity", status: str = "active") -> list[dict]:
        result = self.get(
            TRADING_URL, "/v2/assets", {"asset_class": asset_class, "status": status}
        )
        if not isinstance(result, list):
            raise RuntimeError("unexpected Alpaca assets response")
        return result

    def historical_bars(
        self,
        symbol: str,
        *,
        asset_class: str = "stock",
        timeframe: str = "1Day",
        start: str = "1970-01-01",
        end: str | None = None,
        feed: str = "iex",
        adjustment: str = "raw",
        location: str = "us",
        limit: int = 10_000,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch every requested bar page and return one chronological list."""
        if asset_class not in {"stock", "crypto"}:
            raise ValueError("asset_class must be 'stock' or 'crypto'")
        symbol = symbol.upper()
        token: str | None = None
        seen_tokens: set[str] = set()
        bars: list[dict[str, Any]] = []
        pages = 0
        while True:
            params: dict[str, object] = {
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": limit,
                "page_token": token,
                "sort": "asc",
            }
            if asset_class == "stock":
                path = f"/v2/stocks/{quote(symbol, safe='')}/bars"
                params.update({"feed": feed, "adjustment": adjustment})
                payload = self.get(DATA_URL, path, params)
                batch = payload.get("bars", []) if isinstance(payload, dict) else None
            else:
                path = f"/v1beta3/crypto/{location}/bars"
                params["symbols"] = symbol
                payload = self.get(DATA_URL, path, params)
                groups = payload.get("bars", {}) if isinstance(payload, dict) else None
                batch = groups.get(symbol, []) if isinstance(groups, dict) else None
            if not isinstance(payload, dict) or not isinstance(batch, list):
                raise RuntimeError("unexpected Alpaca historical-bars response")
            bars.extend(batch)
            pages += 1
            next_token = payload.get("next_page_token")
            if next_token is not None and not isinstance(next_token, str):
                raise RuntimeError("invalid Alpaca pagination token")
            if not next_token or (max_pages is not None and pages >= max_pages):
                return bars
            if next_token in seen_tokens:
                raise RuntimeError("Alpaca repeated a pagination token")
            seen_tokens.add(next_token)
            token = next_token

    def stock_snapshots(self, symbols: list[str], feed: str = "iex") -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.get(
            DATA_URL,
            "/v2/stocks/snapshots",
            {"symbols": ",".join(symbol.upper() for symbol in symbols), "feed": feed},
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca stock snapshots response")
        snapshots = result.get("snapshots", result)
        return snapshots if isinstance(snapshots, dict) else {}

    def crypto_snapshots(
        self, symbols: list[str], location: str = "us"
    ) -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.get(
            DATA_URL,
            f"/v1beta3/crypto/{location}/snapshots",
            {"symbols": ",".join(symbol.upper() for symbol in symbols)},
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca crypto snapshots response")
        snapshots = result.get("snapshots", result)
        return snapshots if isinstance(snapshots, dict) else {}

    def crypto_orderbooks(
        self, symbols: list[str], location: str = "us"
    ) -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.get(
            DATA_URL,
            f"/v1beta3/crypto/{location}/latest/orderbooks",
            {"symbols": ",".join(symbol.upper() for symbol in symbols)},
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca crypto order-books response")
        books = result.get("orderbooks", result)
        return books if isinstance(books, dict) else {}

    def latest_stock_quotes(self, symbols: list[str], feed: str = "iex") -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.get(
            DATA_URL,
            "/v2/stocks/quotes/latest",
            {"symbols": ",".join(symbol.upper() for symbol in symbols), "feed": feed},
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca latest-quotes response")
        quotes = result.get("quotes", result)
        return quotes if isinstance(quotes, dict) else {}

    def latest_stock_trades(self, symbols: list[str], feed: str = "iex") -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.get(
            DATA_URL,
            "/v2/stocks/trades/latest",
            {"symbols": ",".join(symbol.upper() for symbol in symbols), "feed": feed},
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca latest-trades response")
        trades = result.get("trades", result)
        return trades if isinstance(trades, dict) else {}

    def news(
        self,
        symbols: list[str] | None = None,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = 50,
        sort: str = "desc",
    ) -> dict[str, Any]:
        """Fetch Alpaca news, including its pagination token when present."""
        result = self.get(
            DATA_URL,
            "/v1beta1/news",
            {
                "symbols": ",".join(symbol.upper() for symbol in symbols or []),
                "start": start,
                "end": end,
                "limit": limit,
                "sort": sort,
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError("unexpected Alpaca news response")
        return result
