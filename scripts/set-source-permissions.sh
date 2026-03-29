#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-fanic}"
APP_GROUP="${APP_GROUP:-fanic}"

if [[ "$#" -gt 0 ]]; then
    ROOT_DIRS=("$@")
else
    ROOT_DIRS=("/opt/fanic/src")
fi

if [[ "${EUID}" -ne 0 ]]; then
    echo "This script must run as root (use sudo)."
    exit 1
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
    echo "User '${APP_USER}' does not exist."
    exit 1
fi

if ! getent group "${APP_GROUP}" >/dev/null 2>&1; then
    echo "Group '${APP_GROUP}' does not exist."
    exit 1
fi

for root_dir in "${ROOT_DIRS[@]}"; do
    if [[ ! -d "${root_dir}" ]]; then
        echo "Directory '${root_dir}' does not exist."
        exit 1
    fi
done

echo "Normalizing group and mode (user=${APP_USER}, group=${APP_GROUP})"
for root_dir in "${ROOT_DIRS[@]}"; do
    echo "- ${root_dir}"
    # Ensure service group can read/traverse all source and template assets.
    chgrp -R "${APP_GROUP}" "${root_dir}"
    find "${root_dir}" -type d -exec chmod 750 {} +
    find "${root_dir}" -type f -exec chmod 640 {} +
done

# Verify non-cache files are readable by the service user.
unreadable_count=0
while IFS= read -r -d '' file_path; do
    if ! sudo -u "${APP_USER}" test -r "${file_path}"; then
        echo "Unreadable by ${APP_USER}: ${file_path}"
        unreadable_count=$((unreadable_count + 1))
    fi
done < <(
    find "${ROOT_DIRS[@]}" -type f ! -path '*/__pycache__/*' -print0
)

if [[ "${unreadable_count}" -gt 0 ]]; then
    echo "Permission verification failed (${unreadable_count} unreadable files)."
    exit 1
fi

echo "Permissions normalized successfully."
