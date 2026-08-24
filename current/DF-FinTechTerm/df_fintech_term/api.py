from __future__ import annotations

import datetime as dt
from typing import Any

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
        snapshots: dict[str, Any] = {}
        for start in range(0, len(symbols), 200):
            batch = symbols[start:start + 200]
            result = self.data(
                "/v2/stocks/snapshots", {"symbols": ",".join(batch), "feed": "iex"}
            )
            if isinstance(result, dict):
                snapshots.update(result.get("snapshots", result))
        return snapshots

    def crypto_snapshot(self) -> dict[str, Any]:
        return self.crypto_snapshots(["BTC/USD"])

    def crypto_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        if not symbols:
            return {}
        result = self.data("/v1beta3/crypto/us/snapshots", {"symbols": ",".join(symbols)})
        return result.get("snapshots", result) if isinstance(result, dict) else {}

    def crypto_orderbook(self) -> dict[str, Any]:
        result = self.data("/v1beta3/crypto/us/latest/orderbooks", {"symbols": "BTC/USD"})
        return result.get("orderbooks", result) if isinstance(result, dict) else {}


def parse_timestamp(value: str | None) -> str:
    if not value:
        return "--"
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return value[:16]
