#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
case "${1:-}" in
    help|-h|--help|indicators|price|tickrs|ticker|tickrs-industry|classify|sentiment|alpaca|services|service|actions|action|catalog|calc|doctor)
        exec ./df-fintechterm "$@"
        ;;
esac
exec python3 -m df_fintech_term
