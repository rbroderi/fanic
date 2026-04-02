#!/usr/bin/env bash
set -euo pipefail

RULE_KEY="${1:-fanic_storage}"
SINCE="${2:-recent}"

if ! command -v ausearch >/dev/null 2>&1; then
  echo "ausearch not found. Install auditd tooling first." >&2
  exit 127
fi

exec ausearch -k "${RULE_KEY}" -i --start "${SINCE}"
