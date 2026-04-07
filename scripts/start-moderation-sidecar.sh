#!/usr/bin/env bash
set -euo pipefail

VENV_BIN="${FANIC_VENV_BIN:-/opt/fanic/.venv/bin}"
GUNICORN_BIN="${FANIC_GUNICORN_BIN:-${VENV_BIN}/gunicorn}"
APP_MODULE="${FANIC_MODERATION_GUNICORN_APP:-fanic.moderation_sidecar:create_app()}"
BIND_ADDR="${FANIC_MODERATION_BIND_ADDR:-unix:/run/fanic/fanic-moderation.sock}"
WORKERS="${FANIC_MODERATION_WORKERS:-1}"
TIMEOUT="${FANIC_MODERATION_TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${FANIC_MODERATION_GRACEFUL_TIMEOUT:-30}"
KEEPALIVE="${FANIC_MODERATION_KEEPALIVE:-5}"
MAX_REQUESTS="${FANIC_MODERATION_MAX_REQUESTS:-2000}"
MAX_REQUESTS_JITTER="${FANIC_MODERATION_MAX_REQUESTS_JITTER:-200}"
PRELOAD_ENABLED="${FANIC_MODERATION_PRELOAD:-1}"
PRELOAD_ARGS=()
if [[ "${PRELOAD_ENABLED}" == "1" ]]; then
	PRELOAD_ARGS+=("--preload")
fi

# Prevent recursion: the sidecar always runs local moderation, never sidecar-to-sidecar HTTP.
export FANIC_MODERATION_SIDECAR_URL=""

if [[ "${BIND_ADDR}" == unix:* ]]; then
	SOCKET_PATH="${BIND_ADDR#unix:}"
	SOCKET_DIR="$(dirname "${SOCKET_PATH}")"
	mkdir -p "${SOCKET_DIR}"
	if [[ -S "${SOCKET_PATH}" ]]; then
		rm -f "${SOCKET_PATH}"
	fi
fi

exec "${GUNICORN_BIN}" \
	"${PRELOAD_ARGS[@]}" \
	--bind "${BIND_ADDR}" \
	--workers "${WORKERS}" \
	--worker-class sync \
	--timeout "${TIMEOUT}" \
	--graceful-timeout "${GRACEFUL_TIMEOUT}" \
	--keep-alive "${KEEPALIVE}" \
	--max-requests "${MAX_REQUESTS}" \
	--max-requests-jitter "${MAX_REQUESTS_JITTER}" \
	--access-logfile - \
	--error-logfile - \
	"${APP_MODULE}"
