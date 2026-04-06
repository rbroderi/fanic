#!/usr/bin/env bash
set -euo pipefail

VENV_BIN="${FANIC_VENV_BIN:-/opt/fanic/.venv/bin}"
GUNICORN_BIN="${FANIC_GUNICORN_BIN:-${VENV_BIN}/gunicorn}"
APP_MODULE="${FANIC_GUNICORN_APP:-fanic.cylinder_main:create_app()}"
BIND_ADDR="${FANIC_BIND_ADDR:-unix:/run/fanic/fanic.sock}"
STARTUP_LOG_PATH="${FANIC_STARTUP_LOG_PATH:-/opt/fanic/startup.log}"

log_startup_event() {
	local message="$1"
	local timestamp
	timestamp="$(date -u +%Y-%m-%dT%H:%M:%S+00:00Z)"
	echo "[${timestamp}] ${message}" >>"${STARTUP_LOG_PATH}" || true
}

on_exit() {
	local exit_code=$?
	log_startup_event "process exit: code=${exit_code}"
}

trap on_exit EXIT

as_positive_int_or_default() {
	local raw_value="$1"
	local default_value="$2"
	if [[ "${raw_value}" =~ ^[0-9]+$ ]] && ((raw_value > 0)); then
		echo "${raw_value}"
		return
	fi
	echo "${default_value}"
}

as_non_negative_int_or_default() {
	local raw_value="$1"
	local default_value="$2"
	if [[ "${raw_value}" =~ ^[0-9]+$ ]]; then
		echo "${raw_value}"
		return
	fi
	echo "${default_value}"
}

read_memory_limit_mb() {
	local cgroup_rel_path=""
	if [[ -r "/proc/self/cgroup" ]]; then
		local cgroup_line
		cgroup_line="$(grep -E '^0::' /proc/self/cgroup 2>/dev/null || true)"
		if [[ -n "${cgroup_line}" ]]; then
			cgroup_rel_path="${cgroup_line#0::}"
		fi
	fi

	local cgroup_memory_max_path=""
	if [[ -n "${cgroup_rel_path}" ]]; then
		cgroup_memory_max_path="/sys/fs/cgroup${cgroup_rel_path}/memory.max"
	fi

	if [[ -n "${cgroup_memory_max_path}" ]] && [[ -r "${cgroup_memory_max_path}" ]]; then
		local cgroup_limit
		cgroup_limit="$(<"${cgroup_memory_max_path}")"
		if [[ "${cgroup_limit}" =~ ^[0-9]+$ ]] && ((cgroup_limit > 0)); then
			echo $((cgroup_limit / 1024 / 1024))
			return
		fi
	fi

	if [[ -r "/sys/fs/cgroup/memory.max" ]]; then
		local root_cgroup_limit
		root_cgroup_limit="$(</sys/fs/cgroup/memory.max)"
		if [[ "${root_cgroup_limit}" =~ ^[0-9]+$ ]] && ((root_cgroup_limit > 0)); then
			echo $((root_cgroup_limit / 1024 / 1024))
			return
		fi
	fi

	if [[ -r "/proc/meminfo" ]]; then
		local mem_total_line
		mem_total_line="$(grep -E '^MemTotal:' /proc/meminfo 2>/dev/null || true)"
		if [[ -n "${mem_total_line}" ]]; then
			local _mem_label
			local _mem_unit
			read -r _mem_label mem_total_kb _mem_unit <<<"${mem_total_line}"
			mem_total_kb="${mem_total_kb:-0}"
			if [[ "${mem_total_kb}" =~ ^[0-9]+$ ]] && ((mem_total_kb > 0)); then
				echo $((mem_total_kb / 1024))
				return
			fi
		fi
	fi

	echo 0
}

calculate_auto_workers() {
	local fallback_workers
	fallback_workers="$(as_positive_int_or_default "${FANIC_GUNICORN_DEFAULT_WORKERS:-3}" "3")"

	local worker_rss_mb
	worker_rss_mb="$(as_positive_int_or_default "${FANIC_GUNICORN_WORKER_RSS_MB:-700}" "700")"
	local reserve_mb
	reserve_mb="$(as_non_negative_int_or_default "${FANIC_GUNICORN_RESERVE_MB:-2048}" "2048")"
	local max_workers
	max_workers="$(as_positive_int_or_default "${FANIC_GUNICORN_MAX_WORKERS:-12}" "12")"
	local min_workers
	min_workers="$(as_positive_int_or_default "${FANIC_GUNICORN_MIN_WORKERS:-1}" "1")"

	local cpu_cap_enabled
	cpu_cap_enabled="$(as_non_negative_int_or_default "${FANIC_GUNICORN_CPU_CAP_ENABLED:-1}" "1")"
	local cpu_multiplier
	cpu_multiplier="$(as_positive_int_or_default "${FANIC_GUNICORN_CPU_MULTIPLIER:-2}" "2")"
	local cpu_offset
	cpu_offset="$(as_non_negative_int_or_default "${FANIC_GUNICORN_CPU_OFFSET:-1}" "1")"

	local total_memory_mb
	total_memory_mb="$(read_memory_limit_mb)"
	if ! [[ "${total_memory_mb}" =~ ^[0-9]+$ ]] || ((total_memory_mb <= 0)); then
		log_startup_event "worker calc: unable to detect memory; using fallback workers=${fallback_workers}"
		echo "${fallback_workers}"
		return
	fi

	local memory_budget_mb=$((total_memory_mb - reserve_mb))
	if ((memory_budget_mb < worker_rss_mb)); then
		memory_budget_mb="${worker_rss_mb}"
	fi

	local workers_from_memory=$((memory_budget_mb / worker_rss_mb))
	if ((workers_from_memory < 1)); then
		workers_from_memory=1
	fi

	local computed_workers="${workers_from_memory}"
	if ((computed_workers > max_workers)); then
		computed_workers="${max_workers}"
	fi

	if ((cpu_cap_enabled > 0)); then
		local cpu_limit="${max_workers}"
		if command -v nproc >/dev/null 2>&1; then
			local cpu_cores
			cpu_cores="$(nproc)"
			if [[ "${cpu_cores}" =~ ^[0-9]+$ ]] && ((cpu_cores > 0)); then
				cpu_limit=$((cpu_cores * cpu_multiplier + cpu_offset))
			fi
		fi
		if ((computed_workers > cpu_limit)); then
			computed_workers="${cpu_limit}"
		fi
	fi

	if ((computed_workers < min_workers)); then
		computed_workers="${min_workers}"
	fi

	log_startup_event "worker calc: total_mb=${total_memory_mb} reserve_mb=${reserve_mb} rss_mb=${worker_rss_mb} max=${max_workers} min=${min_workers} workers=${computed_workers}"
	echo "${computed_workers}"
}

if [[ "${BIND_ADDR}" != unix:* ]]; then
	echo "ERROR: FANIC_BIND_ADDR must use a unix socket (expected unix:/path/to.sock), got '${BIND_ADDR}'" >&2
	exit 1
fi

if [[ -n "${FANIC_GUNICORN_WORKERS:-}" ]]; then
	WORKERS="${FANIC_GUNICORN_WORKERS}"
else
	WORKERS="$(calculate_auto_workers)"
fi

TIMEOUT="${FANIC_GUNICORN_TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${FANIC_GUNICORN_GRACEFUL_TIMEOUT:-30}"
KEEPALIVE="${FANIC_GUNICORN_KEEPALIVE:-5}"
MAX_REQUESTS="${FANIC_GUNICORN_MAX_REQUESTS:-2000}"
MAX_REQUESTS_JITTER="${FANIC_GUNICORN_MAX_REQUESTS_JITTER:-200}"
UMASK_VALUE="${FANIC_GUNICORN_UMASK:-0007}"
PRELOAD_ENABLED="${FANIC_GUNICORN_PRELOAD:-1}"
PRELOAD_ARGS=()
if [[ "${PRELOAD_ENABLED}" == "1" ]]; then
	PRELOAD_ARGS+=("--preload")
fi

SOCKET_PATH="${BIND_ADDR#unix:}"
SOCKET_DIR="$(dirname "${SOCKET_PATH}")"
mkdir -p "${SOCKET_DIR}"
if [[ -S "${SOCKET_PATH}" ]]; then
	rm -f "${SOCKET_PATH}"
fi

log_startup_event "command start: gunicorn"
log_startup_event "gunicorn bind: ${BIND_ADDR} workers=${WORKERS}"

exec "${GUNICORN_BIN}" \
	"${PRELOAD_ARGS[@]}" \
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
