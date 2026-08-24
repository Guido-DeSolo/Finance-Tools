"""Dependency-free decimal finance calculators used by Finance Shell."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def number(value: str) -> Decimal:
    try:
        result = Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError(f"not a number: {value}") from error
    if not result.is_finite():
        raise argparse.ArgumentTypeError("number must be finite")
    return result


def money(value: Decimal) -> str:
    return f"${value.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def percent(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}%"


def compound(args: argparse.Namespace) -> None:
    if args.principal < 0 or args.years < 0 or args.contribution < 0:
        raise SystemExit("principal, years, and contribution cannot be negative")
    monthly_rate = args.rate / Decimal(1200)
    months = int(args.years * 12)
    if args.years * 12 != months:
        raise SystemExit("years must resolve to a whole number of months")
    balance = args.principal
    for _ in range(months):
        balance = balance * (1 + monthly_rate) + args.contribution
    contributed = args.principal + args.contribution * months
    print(f"Ending balance: {money(balance)}")
    print(f"Total contributed: {money(contributed)}")
    print(f"Growth: {money(balance - contributed)}")


def gain(args: argparse.Namespace) -> None:
    if args.cost == 0:
        raise SystemExit("cost cannot be zero")
    change = args.value - args.cost
    print(f"Gain/loss: {money(change)}")
    print(f"Return: {percent(change / args.cost * 100)}")


def budget(args: argparse.Namespace) -> None:
    if args.income < 0 or any(item < 0 for item in args.expenses):
        raise SystemExit("income and expenses cannot be negative")
    spent = sum(args.expenses, Decimal(0))
    remaining = args.income - spent
    print(f"Income: {money(args.income)}")
    print(f"Expenses: {money(spent)}")
    print(f"Remaining: {money(remaining)}")
    if args.income:
        print(f"Savings rate: {percent(remaining / args.income * 100)}")


def allocate(args: argparse.Namespace) -> None:
    if args.total < 0 or not args.weights or any(item < 0 for item in args.weights):
        raise SystemExit("total and weights must be non-negative")
    weight_total = sum(args.weights, Decimal(0))
    if weight_total == 0:
        raise SystemExit("at least one weight must be greater than zero")
    for index, weight in enumerate(args.weights, 1):
        share = args.total * weight / weight_total
        print(f"Allocation {index} ({percent(weight / weight_total * 100)}): {money(share)}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="fsh calc")
    commands = root.add_subparsers(required=True)
    item = commands.add_parser("compound")
    item.add_argument("principal", type=number)
    item.add_argument("rate", type=number)
    item.add_argument("years", type=number)
    item.add_argument("contribution", type=number, nargs="?", default=Decimal(0))
    item.set_defaults(run=compound)
    item = commands.add_parser("gain")
    item.add_argument("cost", type=number)
    item.add_argument("value", type=number)
    item.set_defaults(run=gain)
    item = commands.add_parser("budget")
    item.add_argument("income", type=number)
    item.add_argument("expenses", type=number, nargs="*")
    item.set_defaults(run=budget)
    item = commands.add_parser("allocate")
    item.add_argument("total", type=number)
    item.add_argument("weights", type=number, nargs="+")
    item.set_defaults(run=allocate)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.run(arguments)
