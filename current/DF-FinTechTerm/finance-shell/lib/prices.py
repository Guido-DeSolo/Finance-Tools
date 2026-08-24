"""Explicit, non-persistent live price queries for Finance Shell."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def fetch(url: str, params: dict[str, str]) -> dict:
    request = Request(f"{url}?{urlencode(params)}", headers={"User-Agent": "finance-shell/1"})
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SystemExit(f"price request failed: {error}") from error


def bitcoin() -> None:
    data = fetch(
        "https://api.coingecko.com/api/v3/simple/price",
        {"ids": "bitcoin", "vs_currencies": "usd"},
    )
    try:
        print(f"BTC/USD: ${data['bitcoin']['usd']:,.2f}")
    except (KeyError, TypeError, ValueError) as error:
        raise SystemExit("price provider returned an unexpected response") from error


def silver() -> None:
    key = os.environ.get("METALPRICE_API_KEY")
    if not key:
        raise SystemExit("set METALPRICE_API_KEY before requesting silver prices")
    data = fetch(
        "https://api.metalpriceapi.com/v1/latest",
        {"api_key": key, "base": "USD", "currencies": "XAG"},
    )
    try:
        ounces_per_dollar = float(data["rates"]["USDXAG"])
        print(f"Silver/USD: ${1 / ounces_per_dollar:,.2f} per troy ounce")
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise SystemExit("price provider returned an unexpected response") from error


if __name__ == "__main__":
    {"bitcoin": bitcoin, "silver": silver}[sys.argv[1]]()
