"""One-to-one wrapper for Alpaca's retail account and trading endpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

JSON = dict[str, Any] | list[Any] | str | int | float | bool | None
Params = Mapping[str, Any] | Sequence[tuple[str, Any]] | None

# Current operations in Alpaca's official Trading API specification. Keeping
# this manifest beside the wrapper makes endpoint drift reviewable and tested.
ENDPOINT_COVERAGE: dict[tuple[str, str], str] = {
    ("GET", "/v1/locates"): "list_locates",
    ("POST", "/v1/locates"): "create_locate",
    ("GET", "/v1/locates/{locate_id}"): "get_locate",
    ("GET", "/v1/locates/quotes"): "list_locate_quotes",
    ("GET", "/v2beta1/events/activities"): "stream_account_activities",
    ("GET", "/v2/account"): "get_account",
    ("GET", "/v2/account/activities"): "get_account_activities",
    ("GET", "/v2/account/activities/{activity_type}"): "get_account_activities_by_type",
    ("GET", "/v2/account/configurations"): "get_account_configurations",
    ("PATCH", "/v2/account/configurations"): "update_account_configurations",
    ("GET", "/v2/account/portfolio/history"): "get_portfolio_history",
    ("GET", "/v2/assets"): "list_assets",
    ("GET", "/v2/assets/{symbol_or_asset_id}"): "get_asset",
    ("GET", "/v2/calendar"): "get_calendar",
    ("GET", "/v2/clock"): "get_clock",
    ("GET", "/v2/corporate_actions/announcements"): "list_corporate_action_announcements",
    ("GET", "/v2/corporate_actions/announcements/{id}"): "get_corporate_action_announcement",
    ("GET", "/v2/options/contracts"): "list_option_contracts",
    ("GET", "/v2/options/contracts/{symbol_or_id}"): "get_option_contract",
    ("DELETE", "/v2/orders"): "cancel_all_orders",
    ("GET", "/v2/orders"): "list_orders",
    ("POST", "/v2/orders"): "submit_order",
    ("DELETE", "/v2/orders/{order_id}"): "cancel_order",
    ("GET", "/v2/orders/{order_id}"): "get_order",
    ("PATCH", "/v2/orders/{order_id}"): "replace_order",
    ("GET", "/v2/orders:by_client_order_id"): "get_order_by_client_order_id",
    ("DELETE", "/v2/positions"): "close_all_positions",
    ("GET", "/v2/positions"): "list_positions",
    ("DELETE", "/v2/positions/{symbol_or_asset_id}"): "close_position",
    ("GET", "/v2/positions/{symbol_or_asset_id}"): "get_position",
    ("POST", "/v2/positions/{symbol_or_contract_id}/do-not-exercise"): "do_not_exercise_option",
    ("POST", "/v2/positions/{symbol_or_contract_id}/exercise"): "exercise_option",
    ("POST", "/v2/tokenization/mint"): "mint_tokenized_asset",
    ("GET", "/v2/tokenization/requests"): "list_tokenization_requests",
    ("GET", "/v2/tokenization/requests/{tokenization_request_id}"): "get_tokenization_request",
    ("GET", "/v2/tokenization/requests:by_client_request_id"): "get_tokenization_request_by_client_id",
    ("GET", "/v2/wallets"): "list_wallets",
    ("GET", "/v2/wallets/fees/estimate"): "estimate_wallet_transfer_fee",
    ("GET", "/v2/wallets/transfers"): "list_wallet_transfers",
    ("POST", "/v2/wallets/transfers"): "create_wallet_transfer",
    ("GET", "/v2/wallets/transfers/{transfer_id}"): "get_wallet_transfer",
    ("GET", "/v2/wallets/whitelists"): "list_whitelisted_addresses",
    ("POST", "/v2/wallets/whitelists"): "create_whitelisted_address",
    ("DELETE", "/v2/wallets/whitelists/{whitelisted_address_id}"): "delete_whitelisted_address",
    ("GET", "/v2/watchlists"): "list_watchlists",
    ("POST", "/v2/watchlists"): "create_watchlist",
    ("DELETE", "/v2/watchlists/{watchlist_id}"): "delete_watchlist",
    ("GET", "/v2/watchlists/{watchlist_id}"): "get_watchlist",
    ("POST", "/v2/watchlists/{watchlist_id}"): "add_asset_to_watchlist",
    ("PUT", "/v2/watchlists/{watchlist_id}"): "update_watchlist",
    ("DELETE", "/v2/watchlists/{watchlist_id}/{symbol}"): "remove_asset_from_watchlist",
    ("DELETE", "/v2/watchlists:by_name"): "delete_watchlist_by_name",
    ("GET", "/v2/watchlists:by_name"): "get_watchlist_by_name",
    ("POST", "/v2/watchlists:by_name"): "add_asset_to_watchlist_by_name",
    ("PUT", "/v2/watchlists:by_name"): "update_watchlist_by_name",
    ("GET", "/v3/calendar/{market}"): "get_market_calendar",
    ("GET", "/v3/clock"): "get_market_clock",
}


@dataclass(frozen=True)
class AlpacaResponse:
    """Raw response details for callers that need headers or exact bytes."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> JSON:
        return json.loads(self.body) if self.body else None

    @property
    def request_id(self) -> str | None:
        return self.headers.get("x-request-id")


class AlpacaAPIError(RuntimeError):
    """An HTTP or transport failure from an Alpaca API request."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        method: str | None = None,
        path: str | None = None,
        request_id: str | None = None,
        response: JSON = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.method = method
        self.path = path
        self.request_id = request_id
        self.response = response


def _clean_params(params: Params) -> list[tuple[str, Any]]:
    if params is None:
        return []
    items = params.items() if isinstance(params, Mapping) else params
    result: list[tuple[str, Any]] = []
    for key, value in items:
        if value is None:
            continue
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, (list, tuple, set)):
            value = ",".join(str(item) for item in value)
        result.append((str(key), value))
    return result


def _path(value: str) -> str:
    return quote(str(value), safe="")


class AlpacaAccountClient:
    """Alpaca account/trading client with paper mode enabled by default.

    All responses are returned as Alpaca's decoded JSON without model coercion,
    preserving newly added or obscure response fields. Use :meth:`request` as
    an escape hatch for endpoints introduced after this package version.
    """

    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        *,
        paper: bool = True,
        base_url: str | None = None,
        timeout: float = 30,
        user_agent: str = "finance-tools-alpaca-account/1.0",
    ) -> None:
        if not key_id or not secret_key:
            raise ValueError("key_id and secret_key are required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = (base_url or (self.PAPER_URL if paper else self.LIVE_URL)).rstrip("/")
        self.timeout = timeout
        self.headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
            "Accept": "application/json",
            "User-Agent": user_agent,
        }

    @classmethod
    def from_environment(
        cls, *, paper: bool = True, base_url: str | None = None, timeout: float = 30
    ) -> "AlpacaAccountClient":
        return cls(
            os.environ.get("APCA_API_KEY_ID", ""),
            os.environ.get("APCA_API_SECRET_KEY", ""),
            paper=paper,
            base_url=base_url,
            timeout=timeout,
        )

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        body: Mapping[str, Any] | Sequence[Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AlpacaResponse:
        """Make an exact API request and retain status, headers, and raw body."""
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        query = urlencode(_clean_params(params))
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        encoded = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = {**self.headers, **(headers or {})}
        if encoded is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=encoded, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return AlpacaResponse(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    response.read(),
                )
        except HTTPError as error:
            raw = error.read()
            error.close()
            try:
                detail: JSON = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                detail = raw.decode("utf-8", "replace")
            request_id = error.headers.get("x-request-id") if error.headers else None
            message = detail.get("message") if isinstance(detail, dict) else str(detail or error.reason)
            raise AlpacaAPIError(
                f"Alpaca HTTP {error.code}: {message}",
                status=error.code,
                method=method.upper(),
                path=path,
                request_id=request_id,
                response=detail,
            ) from error
        except (URLError, TimeoutError) as error:
            raise AlpacaAPIError(
                f"Alpaca request failed: {error}", method=method.upper(), path=path
            ) from error

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        body: Mapping[str, Any] | Sequence[Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JSON:
        return self.request_raw(method, path, params=params, body=body, headers=headers).json()

    # Locates and short-sale availability.
    def list_locates(self, **params: Any) -> JSON:
        return self.request("GET", "/v1/locates", params=params)

    def create_locate(self, request: Mapping[str, Any], *, idempotency_key: str | None = None) -> JSON:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.request("POST", "/v1/locates", body=request, headers=headers)

    def list_locate_quotes(self, **params: Any) -> JSON:
        return self.request("GET", "/v1/locates/quotes", params=params)

    def get_locate(self, locate_id: str) -> JSON:
        return self.request("GET", f"/v1/locates/{_path(locate_id)}")

    # Account details, activity ledger, configuration, and performance.
    def get_account(self) -> JSON:
        return self.request("GET", "/v2/account")

    def get_account_activities(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/account/activities", params=params)

    def get_account_activities_by_type(self, activity_type: str, **params: Any) -> JSON:
        return self.request(
            "GET", f"/v2/account/activities/{_path(activity_type)}", params=params
        )

    def get_account_configurations(self) -> JSON:
        return self.request("GET", "/v2/account/configurations")

    def update_account_configurations(self, configuration: Mapping[str, Any]) -> JSON:
        return self.request("PATCH", "/v2/account/configurations", body=configuration)

    def get_portfolio_history(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/account/portfolio/history", params=params)

    # Assets and market schedule metadata exposed by the trading API.
    def list_assets(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/assets", params=params)

    def get_asset(self, symbol_or_asset_id: str) -> JSON:
        return self.request("GET", f"/v2/assets/{_path(symbol_or_asset_id)}")

    def get_calendar(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/calendar", params=params)

    def get_clock(self) -> JSON:
        return self.request("GET", "/v2/clock")

    def get_market_calendar(self, market: str, **params: Any) -> JSON:
        return self.request("GET", f"/v3/calendar/{_path(market)}", params=params)

    def get_market_clock(self, **params: Any) -> JSON:
        return self.request("GET", "/v3/clock", params=params)

    # Corporate actions and option contract metadata.
    def list_corporate_action_announcements(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/corporate_actions/announcements", params=params)

    def get_corporate_action_announcement(self, announcement_id: str) -> JSON:
        return self.request(
            "GET", f"/v2/corporate_actions/announcements/{_path(announcement_id)}"
        )

    def list_option_contracts(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/options/contracts", params=params)

    def get_option_contract(self, symbol_or_id: str) -> JSON:
        return self.request("GET", f"/v2/options/contracts/{_path(symbol_or_id)}")

    # Orders, including multi-leg payloads accepted by Alpaca.
    def list_orders(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/orders", params=params)

    def submit_order(self, order: Mapping[str, Any]) -> JSON:
        return self.request("POST", "/v2/orders", body=order)

    def cancel_all_orders(self) -> JSON:
        return self.request("DELETE", "/v2/orders")

    def get_order(self, order_id: str, **params: Any) -> JSON:
        return self.request("GET", f"/v2/orders/{_path(order_id)}", params=params)

    def replace_order(self, order_id: str, changes: Mapping[str, Any]) -> JSON:
        return self.request("PATCH", f"/v2/orders/{_path(order_id)}", body=changes)

    def cancel_order(self, order_id: str) -> JSON:
        return self.request("DELETE", f"/v2/orders/{_path(order_id)}")

    def get_order_by_client_order_id(self, client_order_id: str) -> JSON:
        return self.request(
            "GET", "/v2/orders:by_client_order_id", params={"client_order_id": client_order_id}
        )

    # Positions and option instructions.
    def list_positions(self) -> JSON:
        return self.request("GET", "/v2/positions")

    def close_all_positions(self, *, cancel_orders: bool | None = None) -> JSON:
        return self.request(
            "DELETE", "/v2/positions", params={"cancel_orders": cancel_orders}
        )

    def get_position(self, symbol_or_asset_id: str) -> JSON:
        return self.request("GET", f"/v2/positions/{_path(symbol_or_asset_id)}")

    def close_position(
        self,
        symbol_or_asset_id: str,
        *,
        qty: str | int | float | None = None,
        percentage: str | int | float | None = None,
    ) -> JSON:
        if qty is not None and percentage is not None:
            raise ValueError("qty and percentage are mutually exclusive")
        return self.request(
            "DELETE",
            f"/v2/positions/{_path(symbol_or_asset_id)}",
            params={"qty": qty, "percentage": percentage},
        )

    def do_not_exercise_option(self, symbol_or_contract_id: str) -> JSON:
        return self.request(
            "POST", f"/v2/positions/{_path(symbol_or_contract_id)}/do-not-exercise"
        )

    def exercise_option(self, symbol_or_contract_id: str) -> JSON:
        return self.request(
            "POST", f"/v2/positions/{_path(symbol_or_contract_id)}/exercise"
        )

    # Tokenization requests.
    def mint_tokenized_asset(self, request: Mapping[str, Any]) -> JSON:
        return self.request("POST", "/v2/tokenization/mint", body=request)

    def list_tokenization_requests(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/tokenization/requests", params=params)

    def get_tokenization_request(self, request_id: str) -> JSON:
        return self.request("GET", f"/v2/tokenization/requests/{_path(request_id)}")

    def get_tokenization_request_by_client_id(self, client_request_id: str) -> JSON:
        return self.request(
            "GET",
            "/v2/tokenization/requests:by_client_request_id",
            params={"client_request_id": client_request_id},
        )

    # Crypto wallets, transfers, fee estimates, and whitelisted addresses.
    def list_wallets(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/wallets", params=params)

    def estimate_wallet_transfer_fee(self, **params: Any) -> JSON:
        return self.request("GET", "/v2/wallets/fees/estimate", params=params)

    def list_wallet_transfers(self) -> JSON:
        return self.request("GET", "/v2/wallets/transfers")

    def create_wallet_transfer(self, transfer: Mapping[str, Any]) -> JSON:
        return self.request("POST", "/v2/wallets/transfers", body=transfer)

    def get_wallet_transfer(self, transfer_id: str) -> JSON:
        return self.request("GET", f"/v2/wallets/transfers/{_path(transfer_id)}")

    def list_whitelisted_addresses(self) -> JSON:
        return self.request("GET", "/v2/wallets/whitelists")

    def create_whitelisted_address(self, address: Mapping[str, Any]) -> JSON:
        return self.request("POST", "/v2/wallets/whitelists", body=address)

    def delete_whitelisted_address(self, address_id: str) -> JSON:
        return self.request("DELETE", f"/v2/wallets/whitelists/{_path(address_id)}")

    # Watchlists by UUID.
    def list_watchlists(self) -> JSON:
        return self.request("GET", "/v2/watchlists")

    def create_watchlist(self, name: str, symbols: Sequence[str] | None = None) -> JSON:
        body: dict[str, Any] = {"name": name}
        if symbols is not None:
            body["symbols"] = list(symbols)
        return self.request("POST", "/v2/watchlists", body=body)

    def get_watchlist(self, watchlist_id: str) -> JSON:
        return self.request("GET", f"/v2/watchlists/{_path(watchlist_id)}")

    def add_asset_to_watchlist(self, watchlist_id: str, symbol: str) -> JSON:
        return self.request(
            "POST", f"/v2/watchlists/{_path(watchlist_id)}", body={"symbol": symbol}
        )

    def update_watchlist(
        self, watchlist_id: str, *, name: str | None = None, symbols: Sequence[str] | None = None
    ) -> JSON:
        return self.request(
            "PUT",
            f"/v2/watchlists/{_path(watchlist_id)}",
            body={key: value for key, value in {"name": name, "symbols": symbols}.items() if value is not None},
        )

    def delete_watchlist(self, watchlist_id: str) -> JSON:
        return self.request("DELETE", f"/v2/watchlists/{_path(watchlist_id)}")

    def remove_asset_from_watchlist(self, watchlist_id: str, symbol: str) -> JSON:
        return self.request(
            "DELETE", f"/v2/watchlists/{_path(watchlist_id)}/{_path(symbol)}"
        )

    # Watchlists by unique name.
    def get_watchlist_by_name(self, name: str) -> JSON:
        return self.request("GET", "/v2/watchlists:by_name", params={"name": name})

    def add_asset_to_watchlist_by_name(self, name: str, symbol: str) -> JSON:
        return self.request(
            "POST", "/v2/watchlists:by_name", params={"name": name}, body={"symbol": symbol}
        )

    def update_watchlist_by_name(
        self, name: str, *, new_name: str | None = None, symbols: Sequence[str] | None = None
    ) -> JSON:
        body = {key: value for key, value in {"name": new_name, "symbols": symbols}.items() if value is not None}
        return self.request("PUT", "/v2/watchlists:by_name", params={"name": name}, body=body)

    def delete_watchlist_by_name(self, name: str) -> JSON:
        return self.request("DELETE", "/v2/watchlists:by_name", params={"name": name})

    def stream_account_activities(self, **params: Any) -> Iterator[JSON]:
        """Yield decoded events from Alpaca's account-activity SSE endpoint."""
        query = urlencode(_clean_params(params))
        path = "/v2beta1/events/activities"
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        request = Request(
            url,
            headers={**self.headers, "Accept": "text/event-stream"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data: list[str] = []
                for raw_line in response:
                    line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
                    if not line:
                        if data:
                            payload = "\n".join(data)
                            yield json.loads(payload)
                            data.clear()
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
                if data:
                    yield json.loads("\n".join(data))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise AlpacaAPIError(
                f"Alpaca activity stream failed: {error}", method="GET", path=path
            ) from error
