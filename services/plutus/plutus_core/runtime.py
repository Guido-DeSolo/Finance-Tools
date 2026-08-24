"""Safe runtime-mode selection shared by Plutus entry points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os


class ExecutionMode(str, Enum):
    BACKTEST = "backtest"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"

    @classmethod
    def parse(cls, value: str | None) -> "ExecutionMode":
        normalized = (value or cls.BACKTEST.value).strip().lower()
        try:
            return cls(normalized)
        except ValueError as error:
            choices = ", ".join(item.value for item in cls)
            raise ValueError(f"PLUTUS_MODE must be one of: {choices}") from error


@dataclass(frozen=True)
class RuntimeConfig:
    mode: ExecutionMode

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(ExecutionMode.parse(os.environ.get("PLUTUS_MODE")))

    @property
    def permits_broker_orders(self) -> bool:
        """Order-capable code must additionally require explicit user consent."""
        return self.mode in {ExecutionMode.PAPER, ExecutionMode.LIVE}

    def require_live_acknowledgement(self, acknowledgement: str | None) -> None:
        if self.mode is ExecutionMode.LIVE and acknowledgement != "LIVE":
            raise RuntimeError("live execution requires the exact acknowledgement LIVE")
