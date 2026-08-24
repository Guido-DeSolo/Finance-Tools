#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "${1:-}" == "fsh" ]]; then
    shift
    exec ./finance-shell/fsh "$@"
fi
exec python3 -m alpaca_terminal
