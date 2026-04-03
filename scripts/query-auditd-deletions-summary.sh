#!/usr/bin/env bash
set -euo pipefail

RULE_KEY="fanic_storage"
SINCE="recent"
PATH_FILTER="/mnt/storage/fanart"

usage() {
  cat <<'EOF'
Usage: scripts/query-auditd-deletions-summary.sh [options]

Options:
  --key <name>          Audit key to query (default: fanic_storage)
  --since <time>        ausearch --start value (default: recent)
  --path <path>         Filter path (default: /mnt/storage/fanart)
  --no-path-filter      Disable path filtering
  -h, --help            Show this help

Examples:
  sudo bash scripts/query-auditd-deletions-summary.sh --since today
  sudo bash scripts/query-auditd-deletions-summary.sh --since "10 minutes ago" --path /mnt/storage/fanart/thumbs
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
    --no-path-filter)
      PATH_FILTER=""
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

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

args=(-k "${RULE_KEY}" -i --start "${SINCE}")
if [[ -n "${PATH_FILTER}" ]]; then
  args+=(-f "${PATH_FILTER}")
fi

set +e
ausearch "${args[@]}" >"${tmp_file}" 2>/dev/null
exit_code=$?
set -e

if [[ "${exit_code}" -ne 0 ]]; then
  if [[ "${exit_code}" -eq 1 ]]; then
    echo "No deletion events found."
    exit 0
  fi
  echo "ausearch failed with exit code ${exit_code}" >&2
  exit "${exit_code}"
fi

if ! grep -q "type=SYSCALL" "${tmp_file}"; then
  echo "No deletion events found."
  exit 0
fi

awk '
BEGIN {
  printf "%-24s %-9s %-8s %-10s %-10s %-22s %-14s %s\n", "time", "syscall", "pid", "auid", "uid", "exe", "comm", "paths"
}

function push_order(id) {
  if (!(id in seen_event)) {
    seen_event[id] = 1
    event_count += 1
    event_order[event_count] = id
  }
}

function add_path(id, label,    key) {
  key = id SUBSEP label
  if (seen_path[key]) {
    return
  }
  seen_path[key] = 1
  if (paths[id] == "") {
    paths[id] = label
  } else {
    paths[id] = paths[id] " | " label
  }
}

{
  line = $0
  if (line !~ /type=/) {
    next
  }

  event_id = ""
  event_time = ""
  if (match(line, /msg=audit\(([^)]*):([0-9]+)\)/, m)) {
    event_time = m[1]
    event_id = m[2]
  }
  if (event_id == "") {
    next
  }

  push_order(event_id)
  if (event_time != "") {
    time_by_id[event_id] = event_time
  }

  if (line ~ /type=SYSCALL/) {
    if (match(line, /syscall=([^[:space:]]+)/, m)) {
      syscall_by_id[event_id] = m[1]
    }
    if (match(line, /pid=([^[:space:]]+)/, m)) {
      pid_by_id[event_id] = m[1]
    }
    if (match(line, /auid=([^[:space:]]+)/, m)) {
      auid_by_id[event_id] = m[1]
    }
    if (match(line, / uid=([^[:space:]]+)/, m)) {
      uid_by_id[event_id] = m[1]
    }
    if (match(line, /exe="([^"]+)"/, m)) {
      exe_by_id[event_id] = m[1]
    } else if (match(line, /exe=([^[:space:]]+)/, m)) {
      exe_by_id[event_id] = m[1]
    }
    if (match(line, /comm="([^"]+)"/, m)) {
      comm_by_id[event_id] = m[1]
    } else if (match(line, /comm=([^[:space:]]+)/, m)) {
      comm_by_id[event_id] = m[1]
    }
    next
  }

  if (line ~ /type=PATH/) {
    path = ""
    nametype = ""
    if (match(line, /name="([^"]+)"/, m)) {
      path = m[1]
    } else if (match(line, /name=([^[:space:]]+)/, m)) {
      path = m[1]
    }
    if (match(line, /nametype=([^[:space:]]+)/, m)) {
      nametype = m[1]
    }
    if (path == "") {
      next
    }

    # Keep output concise: focus on the path entries that denote affected targets.
    if (nametype == "DELETE" || nametype == "CREATE" || nametype == "RENAME_SRC" || nametype == "RENAME_DEST") {
      add_path(event_id, path " (" nametype ")")
    } else if (paths[event_id] == "") {
      add_path(event_id, path)
    }
  }
}

END {
  for (i = 1; i <= event_count; i++) {
    id = event_order[i]
    sc = syscall_by_id[id]
    if (!(sc == "unlink" || sc == "unlinkat" || sc == "rename" || sc == "renameat" || sc == "renameat2" || sc == "rmdir")) {
      continue
    }

    tm = time_by_id[id]
    pd = pid_by_id[id]
    au = auid_by_id[id]
    ui = uid_by_id[id]
    ex = exe_by_id[id]
    cm = comm_by_id[id]
    ps = paths[id]

    if (tm == "") {
      tm = "-"
    }
    if (pd == "") {
      pd = "-"
    }
    if (au == "") {
      au = "-"
    }
    if (ui == "") {
      ui = "-"
    }
    if (ex == "") {
      ex = "-"
    }
    if (cm == "") {
      cm = "-"
    }
    if (ps == "") {
      ps = "-"
    }

    printf "%-24s %-9s %-8s %-10s %-10s %-22s %-14s %s\n", tm, sc, pd, au, ui, ex, cm, ps
  }
}
' "${tmp_file}"