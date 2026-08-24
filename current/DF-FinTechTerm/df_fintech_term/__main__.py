from __future__ import annotations

import sys

from .config import Config
from .ui import Terminal


def main() -> int:
    config = Config.from_env()
    if not config.key_id or not config.secret_key:
        print("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY before starting.", file=sys.stderr)
        return 2
    try:
        Terminal(config).run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
