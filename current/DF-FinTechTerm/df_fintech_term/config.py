from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import os
from pathlib import Path

from .finance_tools import default_finance_shell
from .risk import RiskLimits


def _csv(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x.strip().upper() for x in value.split(",") if x.strip()))


def _nonnegative_decimal(name: str, default: str) -> Decimal:
    try:
        value = Decimal(os.getenv(name, default))
        return value if value.is_finite() and value >= 0 else Decimal(default)
    except (ArithmeticError, ValueError):
        return Decimal(default)


@dataclass(frozen=True)
class Config:
    key_id: str
    secret_key: str
    live: bool
    watchlist: tuple[str, ...]
    refresh_seconds: float
    finance_shell: Path = field(default_factory=default_finance_shell)
    risk_limits: RiskLimits = field(default_factory=RiskLimits)

    @property
    def trading_base(self) -> str:
        return "https://api.alpaca.markets" if self.live else "https://paper-api.alpaca.markets"

    @property
    def finance_database(self) -> Path:
        configured = os.environ.get("ALPACA_DATA_DB")
        return (Path(configured).expanduser() if configured else
                self.finance_shell.parent / "data" / "alpaca.sqlite3")

    @property
    def research_directory(self) -> Path:
        configured = os.environ.get("DF_RESEARCH_OUTPUT_DIR")
        return (Path(configured).expanduser() if configured else
                Path.home() / ".local/share/df-fintechterm/research")

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            key_id=os.getenv("APCA_API_KEY_ID", ""),
            secret_key=os.getenv("APCA_API_SECRET_KEY", ""),
            live=os.getenv("ALPACA_LIVE", "").lower() in {"1", "true", "yes"},
            watchlist=_csv(os.getenv("ALPACA_WATCHLIST", "SPY,AAPL,NVDA")),
            refresh_seconds=max(1.0, float(os.getenv("ALPACA_REFRESH_SECONDS", "3"))),
            finance_shell=default_finance_shell(),
            risk_limits=RiskLimits(
                warn_position_pct=_nonnegative_decimal("DF_RISK_WARN_POSITION_PCT", "20"),
                max_position_pct=_nonnegative_decimal("DF_RISK_MAX_POSITION_PCT", "0"),
                max_order_notional=_nonnegative_decimal("DF_RISK_MAX_ORDER_NOTIONAL", "0"),
                max_daily_loss=_nonnegative_decimal("DF_RISK_MAX_DAILY_LOSS", "0"),
            ),
        )
