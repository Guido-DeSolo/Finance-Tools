from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlencode

import requests


class ApiError(RuntimeError):
    pass


class AlpacaClient:
    def __init__(self, key_id: str, secret_key: str, trading_base: str, timeout: float = 12):
        self.trading_base = trading_base.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
            "Accept": "application/json",
            "User-Agent": "df-fintechterm/0.1",
        })

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise ApiError(f"Network error: {exc}") from exc
        if not response.ok:
            try:
                detail = response.json().get("message", response.text)
            except ValueError:
                detail = response.text
            raise ApiError(f"Alpaca {response.status_code}: {detail[:300]}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def trading(self, path: str, method: str = "GET", **kwargs: Any) -> Any:
        return self._request(method, f"{self.trading_base}{path}", **kwargs)

    def data(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", f"https://data.alpaca.markets{path}", params=params)

    def account(self) -> dict[str, Any]:
        return self.trading("/v2/account")

    def positions(self) -> list[dict[str, Any]]:
        return self.trading("/v2/positions")

    def orders(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.trading("/v2/orders", params={"status": "all", "limit": limit, "direction": "desc"})

    def place_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return self.trading("/v2/orders", "POST", json=order)

    def cancel_order(self, order_id: str) -> None:
        self.trading(f"/v2/orders/{order_id}", "DELETE")

    def close_position(self, symbol: str, percentage: str | None = None) -> Any:
        params = {"percentage": percentage} if percentage else None
        return self.trading(f"/v2/positions/{symbol}", "DELETE", params=params)

    def stock_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.data("/v2/stocks/snapshots", {"symbols": ",".join(symbols), "feed": "iex"})
        return result.get("snapshots", result) if isinstance(result, dict) else {}

    def crypto_snapshot(self) -> dict[str, Any]:
        result = self.data("/v1beta3/crypto/us/snapshots", {"symbols": "BTC/USD"})
        return result.get("snapshots", result) if isinstance(result, dict) else {}

    def crypto_orderbook(self) -> dict[str, Any]:
        result = self.data("/v1beta3/crypto/us/latest/orderbooks", {"symbols": "BTC/USD"})
        return result.get("orderbooks", result) if isinstance(result, dict) else {}


class NewsClient:
    URL = "https://newsdata.io/api/1/latest"

    def __init__(self, api_key: str, timeout: float = 12):
        self.api_key = api_key
        self.timeout = timeout

    def latest(self) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        params = {
            "apikey": self.api_key,
            "country": "us",
            "language": "en",
            "category": "technology,science,environment,domestic,breaking",
        }
        try:
            response = requests.get(self.URL, params=params, timeout=self.timeout,
                                    headers={"User-Agent": "df-fintechterm/0.1"})
        except requests.RequestException as exc:
            raise ApiError(f"News network error: {exc}") from exc
        if not response.ok:
            raise ApiError(f"NewsData {response.status_code}: {response.text[:300]}")
        payload = response.json()
        if payload.get("status") == "error":
            raise ApiError(f"NewsData: {payload.get('results') or payload.get('message')}")
        return payload.get("results") or []


def parse_timestamp(value: str | None) -> str:
    if not value:
        return "--"
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return value[:16]
