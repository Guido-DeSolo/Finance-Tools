from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

from .finance_tools import default_finance_shell


def _csv(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x.strip().upper() for x in value.split(",") if x.strip()))


@dataclass(frozen=True)
class Config:
    key_id: str
    secret_key: str
    newsdata_key: str
    live: bool
    watchlist: tuple[str, ...]
    refresh_seconds: float
    finance_shell: Path = field(default_factory=default_finance_shell)

    @property
    def trading_base(self) -> str:
        return "https://api.alpaca.markets" if self.live else "https://paper-api.alpaca.markets"

    @property
    def finance_database(self) -> Path:
        configured = os.environ.get("ALPACA_DATA_DB")
        return (Path(configured).expanduser() if configured else
                self.finance_shell.parent / "data" / "alpaca.sqlite3")

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            key_id=os.getenv("APCA_API_KEY_ID", ""),
            secret_key=os.getenv("APCA_API_SECRET_KEY", ""),
            newsdata_key=os.getenv("NEWSDATA_API_KEY", ""),
            live=os.getenv("ALPACA_LIVE", "").lower() in {"1", "true", "yes"},
            watchlist=_csv(os.getenv("ALPACA_WATCHLIST", "SPY,AAPL,NVDA")),
            refresh_seconds=max(1.0, float(os.getenv("ALPACA_REFRESH_SECONDS", "3"))),
            finance_shell=default_finance_shell(),
        )
