"""Environment-backed settings for the CLI and scheduled services."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path

from .risk import RiskLimits


def limit(name, default):
    try:
        value = Decimal(os.getenv(name, default))
        return value if value.is_finite() and value >= 0 else Decimal(default)
    except (InvalidOperation, ValueError):
        return Decimal(default)


@dataclass(frozen=True)
class Config:
    key_id: str = ""
    secret_key: str = ""
    live: bool = False
    risk_limits: RiskLimits = RiskLimits()

    @classmethod
    def from_env(cls):
        return cls(os.getenv("APCA_API_KEY_ID", ""), os.getenv("APCA_API_SECRET_KEY", ""),
                   os.getenv("ALPACA_LIVE", "").casefold() in {"1", "true", "yes"},
                   RiskLimits(limit("DF_RISK_WARN_POSITION_PCT", "20"),
                              limit("DF_RISK_MAX_POSITION_PCT", "0"),
                              limit("DF_RISK_MAX_ORDER_NOTIONAL", "0"),
                              limit("DF_RISK_MAX_DAILY_LOSS", "0")))

    @property
    def finance_database(self):
        return Path(os.getenv("FINANCE_DB_FILE", os.getenv("ALPACA_DATA_DB", Path.home()/".local/share/df-fintechterm/market-data/alpaca.sqlite3"))).expanduser()

    @property
    def research_directory(self):
        return Path(os.getenv("DF_RESEARCH_OUTPUT_DIR", Path.home()/".local/share/df-fintechterm/research")).expanduser()

    @property
    def ledger_database(self):
        return Path(os.getenv("DF_LEDGER_DB", Path.home()/".local/share/df-fintechterm/ledger.sqlite3")).expanduser()

    @property
    def trading_base(self):
        return "https://api.alpaca.markets" if self.live else "https://paper-api.alpaca.markets"

    @property
    def openinsider_cache(self):
        return Path(os.getenv("DF_OPENINSIDER_CACHE", Path.home()/".cache/df-fintechterm/openinsider-homepage.json")).expanduser()
