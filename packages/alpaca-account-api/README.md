# Alpaca account API

A dependency-free, importable wrapper with one-to-one coverage of all 57
operations in Alpaca's current retail Trading API specification. Responses are
returned as unmodified decoded JSON so obscure and newly introduced account
fields remain available without waiting for model updates.

This package covers the account and trading API. Market-price and historical
data collection live in the sibling `alpaca-data` package.

## Safety

Paper trading is the default. Live trading requires an explicit `paper=False`.
Methods that submit orders, close positions, exercise options, move crypto, or
change account resources perform the requested action immediately; the wrapper
does not add confirmation prompts.

## Install

```bash
python -m pip install ./packages/alpaca-account-api
```

The package has no third-party runtime dependencies.

## Authentication

```python
from alpaca_account import AlpacaAccountClient

# Reads APCA_API_KEY_ID and APCA_API_SECRET_KEY; paper mode is the default.
client = AlpacaAccountClient.from_environment()

# Live mode must be requested explicitly.
live_client = AlpacaAccountClient.from_environment(paper=False)
```

Credentials can instead be passed directly to `AlpacaAccountClient`. They are
held in memory and are never written to disk.

## Common account lookups

```python
account = client.get_account()
configuration = client.get_account_configurations()
history = client.get_portfolio_history(period="1M", timeframe="1D")
activities = client.get_account_activities(
    category="non_trade_activity", page_size=100
)
positions = client.list_positions()
orders = client.list_orders(status="all", limit=100)
```

The account response is not narrowed to a hand-picked schema. Fields such as
buying-power variants, margin values, day-trade status/counts, option levels,
shorting restrictions, cash values, and any future fields are all preserved.

## Trading

```python
order = client.submit_order({
    "symbol": "AAPL",
    "qty": "1",
    "side": "buy",
    "type": "market",
    "time_in_force": "day",
    "client_order_id": "my-idempotent-order-name",
})

updated = client.replace_order(order["id"], {"qty": "2"})
client.cancel_order(order["id"])
client.close_position("AAPL", percentage="50")
```

Alpaca-compatible payloads for limit, stop, stop-limit, trailing-stop,
notional, fractional, extended-hours, option, and multi-leg orders pass through
unchanged.

## Complete endpoint groups

The public methods provide coverage for:

- Locates and locate quotes
- Full account record, activity ledger by category/type, configurations, and
  portfolio history
- Assets, legacy and v3 clocks/calendars
- Corporate-action announcements and option contracts
- Submit/list/get/replace/cancel orders, including client-order-ID lookup
- List/get/close positions, cancel-before-liquidation, option exercise, and
  do-not-exercise instructions
- Tokenization minting and request tracking
- Crypto wallets, transfer fee estimates, transfers, and address whitelists
- Watchlist operations by UUID and by name
- Server-sent account/trade activity events

`ENDPOINT_COVERAGE` is a machine-readable manifest mapping all 57 official
method/path pairs to their wrapper methods.

## Raw escape hatch and response metadata

For a newly introduced endpoint:

```python
payload = client.request("GET", "/v2/new-endpoint", params={"limit": 10})
```

Use `request_raw` when status, headers, raw bytes, `x-request-id`, or rate-limit
headers matter:

```python
response = client.request_raw("GET", "/v2/account")
print(response.status, response.request_id, response.headers)
account = response.json()
```

API failures raise `AlpacaAPIError` with the HTTP status, method, path, request
ID, and decoded Alpaca response attached.

## Specification baseline

Coverage was audited on 2026-08-24 against the official Alpaca CLI's generated
Trading API specification at commit `f1f635e73247527655da9577128bd63f72c0f8cf`.
The official Python SDK at commit
`45d4b389147a32343f5a0bc45674b44c4e6f3d4d` was used as a secondary behavior
reference. The raw `request` method provides forward compatibility between
coverage audits.

## Tests

```bash
cd packages/alpaca-account-api
python -m unittest discover -s tests -v
```
