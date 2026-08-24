"""Shared configuration loading for broker research scripts."""

import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


def load_settings(required=()):
    """Load settings from BROKER_ENV_PATH (or the project .env) and the environment."""
    env_path = Path(os.environ.get("BROKER_ENV_PATH", DEFAULT_ENV_PATH)).expanduser()
    settings = {
        key: value
        for key, value in dotenv_values(env_path).items()
        if value is not None
    }
    settings.update(
        {key: value for key, value in os.environ.items() if value is not None}
    )

    missing = [key for key in required if not settings.get(key)]
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(f"Missing required configuration: {names}")

    return settings
