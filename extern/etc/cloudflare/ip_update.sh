#!/usr/bin/env bash

set -euo pipefail

# lock it
PIDFILE="/tmp/$(basename "${BASH_SOURCE[0]%.*}.pid")"
exec 200>"${PIDFILE}"
flock -n 200 || (echo "${BASH_SOURCE[0]} script is already running. Aborting . ." && exit 1)
PID=$$
echo "${PID}" 1>&200

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

wget -q https://www.cloudflare.com/ips-v4 -O /tmp/cloudflare-ips-v4
wget -q https://www.cloudflare.com/ips-v6 -O /tmp/cloudflare-ips-v6

while IFS= read -r cfip; do
	/usr/sbin/ufw allow from "${cfip}" to any app "Nginx Full" comment "cloudflare"
done </tmp/cloudflare-ips-v4

while IFS= read -r cfip; do
	/usr/sbin/ufw allow from "${cfip}" to any app "Nginx Full" comment "cloudflare"
done </tmp/cloudflare-ips-v6
