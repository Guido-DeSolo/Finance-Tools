from __future__ import annotations

import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from alpaca_account import (
    ENDPOINT_COVERAGE,
    AlpacaAPIError,
    AlpacaAccountClient,
)


class FakeResponse:
    def __init__(self, body=b"{}", status=200, headers=None):
        self._body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self._body

    def __iter__(self):
        return iter(self._body.splitlines(keepends=True))


class ClientTests(unittest.TestCase):
    def client(self, **changes):
        return AlpacaAccountClient("test-key", "test-secret", **changes)

    def test_manifest_covers_every_current_official_operation(self):
        self.assertEqual(len(ENDPOINT_COVERAGE), 57)
        for operation, method_name in ENDPOINT_COVERAGE.items():
            with self.subTest(operation=operation):
                self.assertTrue(callable(getattr(AlpacaAccountClient, method_name)))

    def test_paper_is_default_and_live_is_explicit(self):
        self.assertEqual(self.client().base_url, AlpacaAccountClient.PAPER_URL)
        self.assertEqual(self.client(paper=False).base_url, AlpacaAccountClient.LIVE_URL)

    def test_transport_preserves_response_metadata_and_encodes_request(self):
        response = FakeResponse(
            json.dumps({"id": "order-1"}).encode(),
            status=201,
            headers={"X-Request-ID": "request-1"},
        )
        with patch("alpaca_account.client.urlopen", return_value=response) as send:
            result = self.client().request_raw(
                "POST",
                "/v2/orders",
                params={"nested": True, "symbols": ["AAPL", "MSFT"], "none": None},
                body={"symbol": "AAPL", "qty": "1"},
            )
        request = send.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertIn("nested=true", request.full_url)
        self.assertIn("symbols=AAPL%2CMSFT", request.full_url)
        self.assertNotIn("none", request.full_url)
        self.assertEqual(json.loads(request.data), {"symbol": "AAPL", "qty": "1"})
        self.assertEqual(request.headers["Apca-api-key-id"], "test-key")
        self.assertEqual(result.status, 201)
        self.assertEqual(result.request_id, "request-1")
        self.assertEqual(result.json()["id"], "order-1")

    def test_api_error_retains_alpaca_details(self):
        error = HTTPError(
            "https://paper-api.alpaca.markets/v2/orders",
            422,
            "unprocessable",
            {"x-request-id": "bad-request"},
            io.BytesIO(b'{"code":42210000,"message":"invalid order"}'),
        )
        with patch("alpaca_account.client.urlopen", side_effect=error):
            with self.assertRaises(AlpacaAPIError) as caught:
                self.client().submit_order({"symbol": "AAPL"})
        self.assertEqual(caught.exception.status, 422)
        self.assertEqual(caught.exception.request_id, "bad-request")
        self.assertEqual(caught.exception.response["code"], 42210000)

    def test_order_and_position_mutations_route_exactly(self):
        client = self.client()
        with patch.object(client, "request", return_value={}) as request:
            client.submit_order({"symbol": "AAPL"})
            client.replace_order("order/id", {"qty": "2"})
            client.cancel_order("order/id")
            client.close_position("BTC/USD", percentage="50")
            client.exercise_option("AAPL option")
        self.assertEqual(request.call_args_list[0].args, ("POST", "/v2/orders"))
        self.assertEqual(request.call_args_list[1].args, ("PATCH", "/v2/orders/order%2Fid"))
        self.assertEqual(request.call_args_list[2].args, ("DELETE", "/v2/orders/order%2Fid"))
        self.assertEqual(request.call_args_list[3].args, ("DELETE", "/v2/positions/BTC%2FUSD"))
        self.assertEqual(request.call_args_list[4].args,
                         ("POST", "/v2/positions/AAPL%20option/exercise"))

    def test_close_position_rejects_conflicting_quantity_forms(self):
        with self.assertRaises(ValueError):
            self.client().close_position("AAPL", qty="1", percentage="50")

    def test_obscure_account_routes_are_exposed(self):
        client = self.client()
        with patch.object(client, "request", return_value={}) as request:
            client.get_account_activities(category="non_trade_activity")
            client.create_locate({"symbol": "HARD", "qty": "100"})
            client.mint_tokenized_asset({"asset_id": "id"})
            client.estimate_wallet_transfer_fee(symbol="BTC", amount="1")
            client.do_not_exercise_option("contract")
            client.get_market_clock(market="us_equity")
        paths = [call.args[1] for call in request.call_args_list]
        self.assertEqual(paths, [
            "/v2/account/activities",
            "/v1/locates",
            "/v2/tokenization/mint",
            "/v2/wallets/fees/estimate",
            "/v2/positions/contract/do-not-exercise",
            "/v3/clock",
        ])

    def test_activity_sse_yields_each_json_event(self):
        payload = b'data: {"stream":"trade_updates","data":{"id":"1"}}\n\n' \
                  b'data: {"stream":"trade_updates","data":{"id":"2"}}\n\n'
        with patch("alpaca_account.client.urlopen", return_value=FakeResponse(payload)):
            events = list(self.client().stream_account_activities(since="now"))
        self.assertEqual([event["data"]["id"] for event in events], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
