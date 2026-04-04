#!/usr/bin/env bash
set -euo pipefail

WATCH_PATH="${FANIC_WATCH_PATH:-/mnt/storage}"
LOG_PATH="${FANIC_WATCH_LOG:-/var/log/fanic/storage-watch.log}"
TIME_FMT="%Y-%m-%dT%H:%M:%S%z"
EVENTS="create,delete,moved_to,moved_from"

if ! command -v inotifywait >/dev/null 2>&1; then
	echo "watch-storage-inotify: inotifywait not found. Install inotify-tools." >&2
	exit 127
fi

if [[ ! -d "${WATCH_PATH}" ]]; then
	echo "watch-storage-inotify: watch path does not exist: ${WATCH_PATH}" >&2
	exit 1
fi

mkdir -p "$(dirname "${LOG_PATH}")"

{
	echo "[$(date +"${TIME_FMT}")] watcher_start path=${WATCH_PATH} events=${EVENTS}"
	inotifywait \
		--monitor \
		--recursive \
		--event "${EVENTS}" \
		--timefmt "${TIME_FMT}" \
		--format '%T|%e|%w%f' \
		"${WATCH_PATH}" | while IFS='|' read -r timestamp events path; do
		printf '[%s] event=%s path=%s\n' "${timestamp}" "${events}" "${path}"
	done
} >>"${LOG_PATH}" 2>&1
