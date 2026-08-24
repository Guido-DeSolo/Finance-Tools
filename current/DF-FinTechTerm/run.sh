#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "${1:-}" == "fsh" ]]; then
    shift
    exec ./finance-shell/fsh "$@"
fi
case "${1:-}" in
    services|service|actions|action|catalog)
        exec ./backend/df-fintechterm "$@"
        ;;
esac
exec python3 -m df_fintech_term
