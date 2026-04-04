#!/usr/bin/env bash
set -euo pipefail

VENV_BIN="${FANIC_VENV_BIN:-/opt/fanic/.venv/bin}"
GUNICORN_BIN="${FANIC_GUNICORN_BIN:-${VENV_BIN}/gunicorn}"
APP_MODULE="${FANIC_GUNICORN_APP:-fanic.cylinder_main:create_app}"
BIND_ADDR="${FANIC_BIND_ADDR:-unix:/run/fanic/fanic.sock}"

if [[ -n "${FANIC_GUNICORN_FACTORY:-}" ]]; then
	if [[ "${FANIC_GUNICORN_FACTORY}" == "1" ]]; then
		FACTORY_FLAG=(--factory)
	else
		FACTORY_FLAG=()
	fi
elif [[ "${APP_MODULE}" == *":app" ]]; then
	FACTORY_FLAG=()
else
	FACTORY_FLAG=(--factory)
fi

if [[ -n "${FANIC_GUNICORN_WORKERS:-}" ]]; then
	WORKERS="${FANIC_GUNICORN_WORKERS}"
else
	if command -v nproc >/dev/null 2>&1; then
		CPU_CORES="$(nproc)"
	else
		CPU_CORES="1"
	fi
	WORKERS="$((CPU_CORES * 2 + 1))"
fi

TIMEOUT="${FANIC_GUNICORN_TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${FANIC_GUNICORN_GRACEFUL_TIMEOUT:-30}"
KEEPALIVE="${FANIC_GUNICORN_KEEPALIVE:-5}"
MAX_REQUESTS="${FANIC_GUNICORN_MAX_REQUESTS:-2000}"
MAX_REQUESTS_JITTER="${FANIC_GUNICORN_MAX_REQUESTS_JITTER:-200}"
UMASK_VALUE="${FANIC_GUNICORN_UMASK:-0007}"

if [[ "${BIND_ADDR}" == unix:* ]]; then
	SOCKET_PATH="${BIND_ADDR#unix:}"
	SOCKET_DIR="$(dirname "${SOCKET_PATH}")"
	mkdir -p "${SOCKET_DIR}"
	if [[ -S "${SOCKET_PATH}" ]]; then
		rm -f "${SOCKET_PATH}"
	fi
fi

exec "${GUNICORN_BIN}" \
	"${FACTORY_FLAG[@]}" \
	--bind "${BIND_ADDR}" \
	--workers "${WORKERS}" \
	--worker-class sync \
	--umask "${UMASK_VALUE}" \
	--timeout "${TIMEOUT}" \
	--graceful-timeout "${GRACEFUL_TIMEOUT}" \
	--keep-alive "${KEEPALIVE}" \
	--max-requests "${MAX_REQUESTS}" \
	--max-requests-jitter "${MAX_REQUESTS_JITTER}" \
	--access-logfile - \
	--error-logfile - \
	"${APP_MODULE}"
