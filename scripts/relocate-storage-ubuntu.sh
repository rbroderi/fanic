#!/usr/bin/env bash
set -euo pipefail

TARGET_STORAGE_ROOT=""
REPO_ROOT=""
ENV_FILE_PATH=""
SKIP_NGINX="false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: scripts/relocate-storage-ubuntu.sh --target-storage-root <path> [options]

Options:
  --target-storage-root <path>   Destination storage root (required)
  --repo-root <path>             Repository root (default: parent of scripts dir)
  --env-file-path <path>         Path to .env file (default: <repo-root>/.env)
  --skip-nginx                   Do not re-run nginx setup script
  -h, --help                     Show this help
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Required command not found: ${cmd}" >&2
    exit 1
  fi
}

resolve_path() {
  local path_value="$1"
  if [[ -z "${path_value}" ]]; then
    echo "Path must not be empty" >&2
    exit 1
  fi
  realpath -m "${path_value}"
}

set_env_value() {
  local env_path="$1"
  local key="$2"
  local value="$3"

  mkdir -p "$(dirname "${env_path}")"
  touch "${env_path}"

  if grep -q "^${key}=" "${env_path}"; then
    sed -i "s|^${key}=.*$|${key}=${value}|" "${env_path}"
  else
    printf '%s=%s\n' "${key}" "${value}" >>"${env_path}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-storage-root)
      TARGET_STORAGE_ROOT="$2"
      shift 2
      ;;
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    --env-file-path)
      ENV_FILE_PATH="$2"
      shift 2
      ;;
    --skip-nginx)
      SKIP_NGINX="true"
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

require_cmd realpath
require_cmd grep
require_cmd sed

if [[ -z "${TARGET_STORAGE_ROOT}" ]]; then
  echo "--target-storage-root is required" >&2
  usage
  exit 1
fi

if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="${DEFAULT_REPO_ROOT}"
fi

REPO_ROOT="$(resolve_path "${REPO_ROOT}")"
TARGET_STORAGE_ROOT="$(resolve_path "${TARGET_STORAGE_ROOT}")"

if [[ -z "${ENV_FILE_PATH}" ]]; then
  ENV_PATH="${REPO_ROOT}/.env"
else
  ENV_PATH="$(resolve_path "${ENV_FILE_PATH}")"
fi

SETUP_NGINX_PATH="${REPO_ROOT}/scripts/setup-nginx-ubuntu.sh"
if [[ ! -f "${SETUP_NGINX_PATH}" ]]; then
  echo "setup-nginx-ubuntu.sh not found at ${SETUP_NGINX_PATH}" >&2
  exit 1
fi

DEFAULT_STORAGE_ROOT="${REPO_ROOT}/src/fanic/storage"
CURRENT_STORAGE_ROOT="${DEFAULT_STORAGE_ROOT}"

if [[ -f "${ENV_PATH}" ]]; then
  existing_data_dir="$(grep '^FANIC_DATA_DIR=' "${ENV_PATH}" | head -n1 | cut -d'=' -f2- || true)"
  if [[ -n "${existing_data_dir}" ]]; then
    CURRENT_STORAGE_ROOT="$(resolve_path "${existing_data_dir}")"
  elif [[ -d "${REPO_ROOT}/src/storage" ]]; then
    CURRENT_STORAGE_ROOT="$(resolve_path "${REPO_ROOT}/src/storage")"
  fi
fi

if [[ ! -d "${CURRENT_STORAGE_ROOT}" && -d "${REPO_ROOT}/src/storage" ]]; then
  CURRENT_STORAGE_ROOT="$(resolve_path "${REPO_ROOT}/src/storage")"
fi

mkdir -p "${TARGET_STORAGE_ROOT}"

if [[ "${CURRENT_STORAGE_ROOT}" != "${TARGET_STORAGE_ROOT}" && -d "${CURRENT_STORAGE_ROOT}" ]]; then
  if find "${TARGET_STORAGE_ROOT}" -mindepth 1 -print -quit | grep -q .; then
    echo "Target storage directory is not empty: ${TARGET_STORAGE_ROOT}" >&2
    exit 1
  fi

  echo "Moving storage from ${CURRENT_STORAGE_ROOT} to ${TARGET_STORAGE_ROOT}"
  parent_dir="$(dirname "${TARGET_STORAGE_ROOT}")"
  mkdir -p "${parent_dir}"

  rm -rf "${TARGET_STORAGE_ROOT}"
  mv "${CURRENT_STORAGE_ROOT}" "${TARGET_STORAGE_ROOT}"
fi

for subdir in cbz works static fanart; do
  mkdir -p "${TARGET_STORAGE_ROOT}/${subdir}"
done

set_env_value "${ENV_PATH}" "FANIC_DATA_DIR" "${TARGET_STORAGE_ROOT}"
echo "Updated FANIC_DATA_DIR in .env to ${TARGET_STORAGE_ROOT}"

if [[ "${SKIP_NGINX}" != "true" ]]; then
  echo "Reconfiguring nginx aliases for new storage path"
  bash "${SETUP_NGINX_PATH}" --repo-root "${REPO_ROOT}" --storage-root "${TARGET_STORAGE_ROOT}" --skip-install --no-prompt
fi

echo "Storage relocation complete"
echo "Current storage root: ${TARGET_STORAGE_ROOT}"
