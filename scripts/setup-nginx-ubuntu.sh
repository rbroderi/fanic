#!/usr/bin/env bash
set -euo pipefail

NGINX_PKG="nginx"
LISTEN_PORT="8080"
WSGI_UPSTREAM="unix:/run/fanic/fanic.sock:"
WSGI_HOST=""
WSGI_PORT=""
SERVER_NAME="localhost"
REPO_ROOT=""
STORAGE_ROOT=""
SKIP_INSTALL="false"
NO_PROMPT="false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
	cat <<'EOF'
Usage: scripts/setup-nginx-ubuntu.sh [options]

Options:
  --listen-port <port>      Local nginx listen port (default: 8080)
	--wsgi-upstream <target>  Upstream target (default: unix:/run/fanic/fanic.sock:)
														Example TCP: 127.0.0.1:8000
	--wsgi-host <host>        Upstream WSGI host (legacy helper with --wsgi-port)
	--wsgi-port <port>        Upstream WSGI port (legacy helper with --wsgi-host)
  --server-name <name>      nginx server_name (default: localhost)
  --repo-root <path>        Repository root (default: parent of scripts dir)
  --storage-root <path>     FANIC storage root (default: <repo-root>/src/storage)
  --skip-install            Do not install nginx with apt
  --no-prompt               Non-interactive mode
  -h, --help                Show this help
EOF
}

prompt_default() {
	local message="$1"
	local default="$2"
	local value
	read -r -p "${message} [${default}]: " value
	if [[ -z "${value}" ]]; then
		printf '%s\n' "${default}"
	else
		printf '%s\n' "${value}"
	fi
}

require_cmd() {
	local cmd="$1"
	if ! command -v "${cmd}" >/dev/null 2>&1; then
		echo "Required command not found: ${cmd}" >&2
		exit 1
	fi
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--listen-port)
		LISTEN_PORT="$2"
		shift 2
		;;
	--wsgi-host)
		WSGI_HOST="$2"
		shift 2
		;;
	--wsgi-port)
		WSGI_PORT="$2"
		shift 2
		;;
	--wsgi-upstream)
		WSGI_UPSTREAM="$2"
		shift 2
		;;
	--server-name)
		SERVER_NAME="$2"
		shift 2
		;;
	--repo-root)
		REPO_ROOT="$2"
		shift 2
		;;
	--storage-root)
		STORAGE_ROOT="$2"
		shift 2
		;;
	--skip-install)
		SKIP_INSTALL="true"
		shift
		;;
	--no-prompt)
		NO_PROMPT="true"
		shift
		;;
	-h | --help)
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

if [[ -z "${REPO_ROOT}" ]]; then
	REPO_ROOT="${DEFAULT_REPO_ROOT}"
fi
REPO_ROOT="$(realpath "${REPO_ROOT}")"

if [[ -z "${STORAGE_ROOT}" ]]; then
	STORAGE_ROOT="${REPO_ROOT}/src/storage"
fi
STORAGE_ROOT="$(realpath "${STORAGE_ROOT}")"

if [[ "${NO_PROMPT}" != "true" ]]; then
	echo
	echo "FANIC nginx setup for Ubuntu"
	echo "This config serves /cbz and /static from storage and proxies all other routes to WSGI."
	echo

	LISTEN_PORT="$(prompt_default "Local listen port" "${LISTEN_PORT}")"
	WSGI_UPSTREAM="$(prompt_default "WSGI upstream (unix:/path.sock: or host:port)" "${WSGI_UPSTREAM}")"
	SERVER_NAME="$(prompt_default "nginx server_name" "${SERVER_NAME}")"
	REPO_ROOT="$(prompt_default "Repo root" "${REPO_ROOT}")"
	STORAGE_ROOT="$(prompt_default "Storage root" "${STORAGE_ROOT}")"
	INSTALL_ANSWER="$(prompt_default "Install nginx with apt if missing? (yes/no)" "yes")"
	if [[ "${INSTALL_ANSWER,,}" != "yes" ]]; then
		SKIP_INSTALL="true"
	fi
fi

REPO_ROOT="$(realpath "${REPO_ROOT}")"
STORAGE_ROOT="$(realpath "${STORAGE_ROOT}")"

if [[ -n "${WSGI_HOST}" || -n "${WSGI_PORT}" ]]; then
	resolved_host="${WSGI_HOST:-127.0.0.1}"
	resolved_port="${WSGI_PORT:-8000}"
	WSGI_UPSTREAM="${resolved_host}:${resolved_port}"
fi

if [[ "${WSGI_UPSTREAM}" == unix:* && "${WSGI_UPSTREAM}" != *: ]]; then
	WSGI_UPSTREAM="${WSGI_UPSTREAM}:"
fi

CBZ_DIR="${STORAGE_ROOT}/cbz"
STATIC_DIR="${STORAGE_ROOT}/static"
FANART_DIR="${STORAGE_ROOT}/fanart"
WORKS_DIR="${STORAGE_ROOT}/works"

for dir_path in "${CBZ_DIR}" "${STATIC_DIR}" "${FANART_DIR}" "${WORKS_DIR}"; do
	if [[ ! -d "${dir_path}" ]]; then
		echo "Expected directory not found: ${dir_path}" >&2
		exit 1
	fi
done

SUDO=""
if [[ "${EUID}" -ne 0 ]]; then
	require_cmd sudo
	SUDO="sudo"
fi

if [[ "${SKIP_INSTALL}" != "true" ]]; then
	if ! command -v nginx >/dev/null 2>&1; then
		echo "Installing nginx package"
		${SUDO} apt-get update
		${SUDO} apt-get install -y "${NGINX_PKG}"
	fi
fi

require_cmd nginx

SITES_AVAILABLE="/etc/nginx/sites-available"
SITES_ENABLED="/etc/nginx/sites-enabled"
CONF_PATH="${SITES_AVAILABLE}/fanic.conf"
DEFAULT_SITE="${SITES_ENABLED}/default"
ENABLED_LINK="${SITES_ENABLED}/fanic.conf"

if [[ -f "${CONF_PATH}" ]]; then
	backup_path="${CONF_PATH}.bak.$(date +%Y%m%d%H%M%S)"
	${SUDO} cp "${CONF_PATH}" "${backup_path}"
	echo "Backed up existing config to ${backup_path}"
fi

cat <<EOF | ${SUDO} tee "${CONF_PATH}" >/dev/null
server {
    listen 127.0.0.1:${LISTEN_PORT};
    server_name ${SERVER_NAME};

  error_page 502 503 504 =200 /upstream-unavailable.html;

  location = /upstream-unavailable.html {
    internal;
    root /var/www/fanic-errors;
    default_type text/html;
    add_header Cache-Control "no-store" always;
  }

    location ~* ^/(?:fanic\.db|storage/|.*\.(?:db|sqlite|sqlite3))$ {
        return 404;
    }

    location = /robots.txt {
      default_type text/plain;
      add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
      return 200 "User-agent: *\nDisallow: /\n";
    }

    location /cbz/ {
        alias ${CBZ_DIR}/;
        try_files \$uri =404;
        access_log off;
    }

    location ^~ /static/fanart/images/ {
      alias ${FANART_DIR}/images/;
      try_files \$uri \$uri/ =404;
      access_log off;
    }

    location ^~ /static/fanart/thumbs/ {
      alias ${FANART_DIR}/thumbs/;
      try_files \$uri \$uri/ =404;
      access_log off;
    }

    location ~ ^/static/([^/]+)/(pages|thumbs)/(.*)$ {
      alias ${WORKS_DIR}/\$1/\$2/\$3;
      access_log off;
    }

    location /static/ {
      alias ${STATIC_DIR}/;
      try_files \$uri =404;
        access_log off;
      add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location / {
				proxy_pass http://${WSGI_UPSTREAM};
        proxy_http_version 1.1;
      proxy_intercept_errors on;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

echo "Wrote nginx config to ${CONF_PATH}"

if [[ -L "${DEFAULT_SITE}" || -f "${DEFAULT_SITE}" ]]; then
	${SUDO} rm -f "${DEFAULT_SITE}"
fi

if [[ -L "${ENABLED_LINK}" || -f "${ENABLED_LINK}" ]]; then
	${SUDO} rm -f "${ENABLED_LINK}"
fi
${SUDO} ln -s "${CONF_PATH}" "${ENABLED_LINK}"

echo "Validating nginx config"
${SUDO} nginx -t

if ${SUDO} systemctl is-active --quiet nginx; then
	echo "Reloading nginx"
	${SUDO} systemctl reload nginx
else
	echo "Starting nginx"
	${SUDO} systemctl enable --now nginx
fi

echo
echo "Setup complete"
echo "repo root: ${REPO_ROOT}"
echo "serving /cbz from: ${CBZ_DIR}"
echo "serving /static from: ${STATIC_DIR}"
echo "serving /static/fanart/images from: ${FANART_DIR}/images"
echo "serving /static/fanart/thumbs from: ${FANART_DIR}/thumbs"
echo "serving /static/{work_id}/(pages|thumbs) from: ${WORKS_DIR}/{work_id}/..."
echo "proxying dynamic routes to: http://${WSGI_UPSTREAM}"
echo "open: http://127.0.0.1:${LISTEN_PORT}"
echo
echo "Common commands:"
echo "  sudo nginx -t"
echo "  sudo systemctl reload nginx"
echo "  sudo systemctl stop nginx"
