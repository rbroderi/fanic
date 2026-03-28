#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="${repo_root}/static"
dst_dir="${FANIC_STATIC_TARGET:-/mnt/storage/static}"

if [[ ! -d "${src_dir}" ]]; then
  echo "sync-static: repo static missing, skipping: ${src_dir}"
  exit 0
fi

if [[ -L "${dst_dir}" ]]; then
  rm "${dst_dir}"
fi

mkdir -p "${dst_dir}"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "${src_dir}/" "${dst_dir}/"
else
  find "${dst_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -a "${src_dir}/." "${dst_dir}/"
fi

echo "sync-static: synced ${src_dir} -> ${dst_dir}"
