#!/usr/bin/env bash
set -euo pipefail

matches="$(git ls-files -z | tr '\0' '\n' | rg '(^|/)fanic\.db$' || true)"

if [[ -n "${matches}" ]]; then
  echo "forbid-fanic-db: tracked fanic.db path(s) detected:" >&2
  echo "${matches}" >&2
  echo "Remove these from git history/index and keep them ignored." >&2
  exit 1
fi

echo "forbid-fanic-db: ok"