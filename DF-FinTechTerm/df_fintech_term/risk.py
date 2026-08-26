"""Deterministic pre-trade portfolio impact and configurable risk limits."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


@dataclass(frozen=True)
class RiskLimits:
    warn_position_pct: Decimal = Decimal("20")
    max_position_pct: Decimal = Decimal("0")
    max_order_notional: Decimal = Decimal("0")
    max_daily_loss: Decimal = Decimal("0")


@dataclass(frozen=True)
class RiskAssessment:
    estimated_notional: Decimal | None
    reference_price: Decimal | None
    projected_position_value: Decimal | None
    projected_position_pct: Decimal | None
    projected_buying_power: Decimal | None
    warnings: tuple[str, ...]
    violations: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        notional = f"${self.estimated_notional:,.2f}" if self.estimated_notional is not None else "unknown notional"
        weight = f"{self.projected_position_pct:.1f}% position" if self.projected_position_pct is not None else "unknown weight"
        buying_power = (
            f"${self.projected_buying_power:,.2f} BP"
            if self.projected_buying_power is not None else "unknown BP"
        )
        notes = self.violations or self.warnings
        suffix = f" · {'; '.join(notes)}" if notes else ""
        return f"Risk preview: {notional} · {weight} · {buying_power}{suffix}"


def portfolio_risk_line(account: dict[str, Any], positions: list[dict[str, Any]]) -> str:
    """Compact dashboard summary of current exposure and concentration."""
    equity = _decimal(account.get("equity")) or Decimal("0")
    last_equity = _decimal(account.get("last_equity")) or equity
    values = [
        (str(item.get("symbol") or "--"), abs(_decimal(item.get("market_value")) or Decimal("0")))
        for item in positions
    ]
    gross = sum((value for _, value in values), Decimal("0"))
    largest_symbol, largest_value = max(values, key=lambda item: item[1], default=("--", Decimal("0")))
    gross_pct = gross / equity * 100 if equity > 0 else Decimal("0")
    largest_pct = largest_value / equity * 100 if equity > 0 else Decimal("0")
    daily = equity - last_equity
    return (
        f"RISK  Day {daily:+,.2f} · Gross {gross_pct:.1f}% · "
        f"Largest {largest_symbol} {largest_pct:.1f}%"
    )


def assess_order(
    order: dict[str, Any],
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    snapshot: dict[str, Any],
    limits: RiskLimits,
) -> RiskAssessment:
    symbol = str(order.get("symbol") or "").upper()
    side = str(order.get("side") or "").lower()
    position = next((item for item in positions if str(item.get("symbol") or "").upper() == symbol), {})
    quote = snapshot.get("latestQuote") or {}
    trade = snapshot.get("latestTrade") or {}
    price = _decimal(order.get("limit_price") or order.get("stop_price"))
    if price is None:
        price = _decimal(quote.get("ap") if side == "buy" else quote.get("bp"))
    if price is None:
        price = _decimal(trade.get("p") or position.get("current_price"))

    notional = _decimal(order.get("notional"))
    quantity = _decimal(order.get("qty"))
    warnings: list[str] = []
    violations: list[str] = []
    if "notional" in order and (notional is None or notional <= 0):
        violations.append("notional must be a positive number")
    if "qty" in order and (quantity is None or quantity <= 0):
        violations.append("quantity must be a positive number")
    if notional is None and quantity is not None and price is not None:
        notional = quantity * price
    if notional is None or notional <= 0:
        warnings.append("impact unavailable: no valid reference price")

    equity = _decimal(account.get("equity"))
    buying_power = _decimal(account.get("buying_power"))
    current_value = abs(_decimal(position.get("market_value")) or Decimal("0"))
    held_quantity = _decimal(position.get("qty")) or Decimal("0")
    projected_value = None
    projected_pct = None
    projected_bp = None
    if notional is not None and notional > 0:
        if side == "buy" and held_quantity < 0:
            projected_value = max(Decimal("0"), current_value - notional)
        else:
            projected_value = current_value + notional if side == "buy" else max(Decimal("0"), current_value - notional)
        if equity and equity > 0:
            projected_pct = projected_value / equity * 100
        if buying_power is not None:
            projected_bp = buying_power - notional if side == "buy" else buying_power
            if side == "buy" and projected_bp < 0:
                violations.append("order exceeds buying power")
        if side == "buy" and limits.max_order_notional > 0 and notional > limits.max_order_notional:
            violations.append(f"order exceeds ${limits.max_order_notional:,.2f} limit")
    if side == "sell" and quantity is not None and quantity > held_quantity:
        violations.append(f"sell quantity exceeds {held_quantity:g} held")
    if side == "sell" and order.get("notional") is not None and notional is not None and notional > current_value:
        violations.append("sell notional exceeds current position value")
    if side == "buy" and projected_pct is not None:
        if limits.max_position_pct > 0 and projected_pct > limits.max_position_pct:
            violations.append(f"position exceeds {limits.max_position_pct:g}% limit")
        elif limits.warn_position_pct > 0 and projected_pct > limits.warn_position_pct:
            warnings.append(f"concentration above {limits.warn_position_pct:g}%")

    last_equity = _decimal(account.get("last_equity"))
    if side == "buy" and limits.max_daily_loss > 0 and equity is not None and last_equity is not None:
        daily_loss = max(Decimal("0"), last_equity - equity)
        if daily_loss >= limits.max_daily_loss:
            violations.append(f"daily loss limit reached (${daily_loss:,.2f})")

    return RiskAssessment(
        notional, price, projected_value, projected_pct, projected_bp,
        tuple(warnings), tuple(violations),
    )
