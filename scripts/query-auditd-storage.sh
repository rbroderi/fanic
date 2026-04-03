#!/usr/bin/env bash
set -euo pipefail

RULE_KEY="fanic_storage"
SINCE="recent"
PATH_FILTER=""
DELETIONS_ONLY="0"

usage() {
  cat <<'EOF'
Usage: scripts/query-auditd-storage.sh [options]

Options:
  --key <name>          Audit key to query (default: fanic_storage)
  --since <time>        ausearch --start value (default: recent)
  --path <path>         Filter to a specific file/dir path
  --deletions           Filter to delete/rename events only
  -h, --help            Show this help

Examples:
  sudo bash scripts/query-auditd-storage.sh --since today
  sudo bash scripts/query-auditd-storage.sh --deletions --since today --path /mnt/storage/fanart
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)
      RULE_KEY="$2"
      shift 2
      ;;
    --since)
      SINCE="$2"
      shift 2
      ;;
    --path)
      PATH_FILTER="$2"
      shift 2
      ;;
    --deletions)
      DELETIONS_ONLY="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v ausearch >/dev/null 2>&1; then
  echo "ausearch not found. Install auditd tooling first." >&2
  exit 127
fi

ARGS=(-k "${RULE_KEY}" -i --start "${SINCE}")
if [[ -n "${PATH_FILTER}" ]]; then
  ARGS+=(-f "${PATH_FILTER}")
fi

if [[ "${DELETIONS_ONLY}" != "1" ]]; then
  exec ausearch "${ARGS[@]}"
fi

ausearch "${ARGS[@]}" | awk '
BEGIN {
  RS = ""
  ORS = "\n\n"
}
{
  syscall_match = ($0 ~ /type=SYSCALL[^\n]*syscall=(unlink|unlinkat|rename|renameat|renameat2|rmdir)([^[:alnum:]_]|$)/)
  path_match = ($0 ~ /type=PATH[^\n]*nametype=(DELETE|RENAME_SRC|RENAME_DEST)([^[:alnum:]_]|$)/)
  if (syscall_match || path_match) {
    print $0
  }
}
'
