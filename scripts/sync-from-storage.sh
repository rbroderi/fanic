#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src_dir="${FANIC_STATIC_SOURCE:-/mnt/storage/static}"
dst_dir="${repo_root}/static"

if [[ ! -d "${src_dir}" ]]; then
	echo "sync-static: source missing, skipping: ${src_dir}"
	exit 0
fi

if [[ ! -d "${dst_dir}" ]]; then
	echo "sync-static: destination missing, skipping: ${dst_dir}"
	exit 0
fi

if command -v rsync >/dev/null 2>&1; then
	rsync -a --delete --delete-excluded \
		--exclude='*.js' \
		--exclude='*.js.map' \
		--exclude='*.css' \
		--exclude='*.css.map' \
		"${src_dir}/" "${dst_dir}/"
else
	find "${dst_dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
	while IFS= read -r -d '' rel_path; do
		target_path="${dst_dir}/${rel_path#./}"
		mkdir -p "$(dirname "${target_path}")"
		cp -a "${src_dir}/${rel_path#./}" "${target_path}"
	done < <(
		cd "${src_dir}"
		find . -type f ! -name '*.js' ! -name '*.js.map' ! -name '*.css' ! -name '*.css.map' -print0
	)
fi

echo "sync-static: mirrored ${src_dir} -> ${dst_dir} (excluding *.js, *.js.map, *.css, *.css.map)"
