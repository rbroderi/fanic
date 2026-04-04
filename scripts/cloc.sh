#!/usr/bin/env bash
set -euo pipefail

mapfile -t dirs < <(
	find . -maxdepth 1 -type d \
		! -name '.' \
		! -name '.*' \
		! -name 'node*'
)

cloc "${dirs[@]}"
