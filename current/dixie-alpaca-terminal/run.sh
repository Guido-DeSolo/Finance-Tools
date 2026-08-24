#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "${1:-}" == "fsh" ]]; then
    shift
    exec ./finance-shell/fsh "$@"
fi
if [[ "${1:-}" == "plutus" ]]; then
    shift
    exec ../../services/plutus/plutus "$@"
fi
exec python3 -m alpaca_terminal
