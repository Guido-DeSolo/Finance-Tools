"""Small, guarded Alpaca order CLI."""

import argparse
import json
import os
import sys
import threading

from .api import AlpacaClient, ApiError
from .config import Config
from .ledger import Ledger
from .order_stream import OrderUpdateStream
from .risk import assess_order


def setup(live):
    key, secret = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError("set APCA_API_KEY_ID and APCA_API_SECRET_KEY")
    base = "https://api.alpaca.markets" if live else "https://paper-api.alpaca.markets"
    cfg = Config.from_env()
    return cfg, AlpacaClient(key, secret, base), Ledger(cfg.ledger_database, "live" if live else "paper")


def confirm(text, live, yes):
    if not sys.stdin.isatty():
        if yes and not live: return
        raise ValueError("confirmation required; use --yes for paper orders or run interactively for live")
    token = input(f"{text} Type {'LIVE' if live else 'YES'}: ")
    if token != ("LIVE" if live else "YES"):
        raise ValueError("canceled")


def emit(value):
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def run(args):
    cfg, api, ledger = setup(args.live)
    if args.cmd == "account":
        emit({"account": api.account(), "positions": api.positions()})
    elif args.cmd == "list":
        emit(api.orders(args.limit))
    elif args.cmd == "watch":
        stop = threading.Event()
        try:
            OrderUpdateStream(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"), api.trading_base).run(
                stop, lambda event: emit(event), lambda state: print(state, file=sys.stderr, flush=True))
        except KeyboardInterrupt:
            stop.set()
    elif args.cmd in {"buy", "sell"}:
        symbol, side = args.symbol.upper(), args.cmd
        order = {"symbol": symbol, "side": side, "type": args.type, "time_in_force": args.tif}
        order["notional" if args.notional else "qty"] = args.notional or args.quantity
        if args.limit_price: order["limit_price"] = args.limit_price
        if args.stop_price: order["stop_price"] = args.stop_price
        account, positions = api.account(), api.positions()
        try:
            snap = api.crypto_snapshots([symbol]) if "/" in symbol else api.stock_snapshots([symbol])
            snapshot = snap.get(symbol) or snap.get(symbol.replace("/", "")) or {}
        except ApiError:
            snapshot = {}
        risk = assess_order(order, account, positions, snapshot, cfg.risk_limits)
        print(risk.summary())
        if not risk.allowed: raise ValueError("order blocked: " + "; ".join(risk.violations))
        confirm(f"{side.upper()} {symbol} {order.get('qty', '$'+str(order.get('notional')))} {args.type}.", args.live, args.yes)
        audit = {"order": order, "risk": {"allowed": risk.allowed, "warnings": risk.warnings,
                 "violations": risk.violations, "estimated_notional": risk.estimated_notional}}
        ledger.record("decision", "order_authorized", audit)
        try:
            result = api.place_order(order)
            ledger.record("broker", "order_submitted", {"order": result})
            emit(result)
        except ApiError as error:
            ledger.record("broker", "order_submission_failed", {"order": order, "error": str(error)})
            raise
    elif args.cmd == "cancel":
        confirm(f"Cancel order {args.id}.", args.live, args.yes)
        ledger.record("decision", "cancel_authorized", {"id": args.id})
        api.cancel_order(args.id)
        ledger.record("broker", "cancel_requested", {"id": args.id})
    elif args.cmd == "close":
        confirm(f"Close {args.symbol.upper()}.", args.live, args.yes)
        ledger.record("decision", "close_authorized", {"symbol": args.symbol.upper()})
        api.close_position(args.symbol.upper(), args.percentage)
        ledger.record("broker", "close_requested", {"symbol": args.symbol.upper()})


def main():
    p = argparse.ArgumentParser(prog="df-fintechterm orders")
    p.add_argument("--live", action="store_true", help="target the live Alpaca account")
    p.add_argument("--yes", action="store_true", help="skip paper confirmation in scripts")
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("account"); o = s.add_parser("list"); o.add_argument("--limit", type=int, default=50)
    s.add_parser("watch")
    for side in ("buy", "sell"):
        o = s.add_parser(side); o.add_argument("symbol"); amount = o.add_mutually_exclusive_group(required=True)
        amount.add_argument("--quantity"); amount.add_argument("--notional")
        o.add_argument("--type", choices=("market", "limit", "stop", "stop_limit"), default="market")
        o.add_argument("--tif", choices=("day", "gtc", "opg", "cls", "ioc", "fok"), default="day")
        o.add_argument("--limit-price"); o.add_argument("--stop-price")
    o = s.add_parser("cancel"); o.add_argument("id")
    o = s.add_parser("close"); o.add_argument("symbol"); o.add_argument("--percentage")
    args = p.parse_args()
    try: run(args)
    except (ApiError, OSError, ValueError) as e: p.exit(2, f"orders: {e}\n")


if __name__ == "__main__": main()
