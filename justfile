set shell := ["bash", "-lc"]

_default:
    @just --list

# Initialize the SQLite database schema.
init-db:
    uv run src/fanic/main.py init-db

# Run runtime database migrations without resetting data.
migrate-db:
    uv run src/fanic/main.py migrate-db

# Launch the local development server.
serve:
    npm run frontend:build; FANIC_GUNICORN_WORKERS=1 bash scripts/start-gunicorn.sh

# Run autopep695 in check or format mode.
autopep695 mode="check":
    mode="{{ mode }}"; if [ "$mode" != "check" ] && [ "$mode" != "format" ]; then echo "mode must be 'check' or 'format'"; exit 1; fi; uv run autopep695 "$mode" src

# Run the same Ruff checks as the GitHub workflow.
ruff-ci:
    uvx ruff check --exclude typings src tests; uvx ruff format --check --exclude typings src tests

# Run Ruff in pre-commit mode (auto-fix, auto-format, then lint check).
ruff-precommit:
    uvx ruff check --fix --exclude typings src tests; uvx ruff format --exclude typings src tests; uvx ruff check --exclude typings src tests

# Run Python type checking with basedpyright.
py-typecheck:
    uvx basedpyright

# Run Python type checking directly.
basedpyright:
    uv run basedpyright

# Run prek hooks against all files.
prek:
    bash scripts/sync-from-storage.sh; uv run prek run --all-files; uv run prek run --all-files

# Run pytest with coverage for the src package.
test *args:
    if sudo systemctl cat fanic >/dev/null 2>&1 && sudo systemctl is-active --quiet fanic; then sudo systemctl stop fanic; fi; args='{{ args }}'; if [ -n "$args" ]; then FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-report=term-missing {{ args }}; else FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-report= --ignore=tests/test_moderation_media.py && FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-append --cov-report=term-missing tests/test_moderation_media.py; fi

# Install and configure nginx for FANIC.
setup-nginx:
    bash scripts/setup-nginx-ubuntu.sh

# Relocate storage root, update .env FANIC_DATA_DIR, and refresh nginx aliases.
relocate-storage target:
    bash scripts/relocate-storage-ubuntu.sh --target-storage-root "{{ target }}"

# Summarize storage deletion/rename audit events with actor/process metadata.
audit-deletions since="recent" path="/mnt/storage/fanart":
    bash scripts/query-auditd-deletions-summary.sh --since "{{ since }}" --path "{{ path }}"

# Start nginx (or reload if already running) and then run the WSGI server.
start:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found. Run just setup-nginx first."; exit 1; fi; if ! sudo nginx -t; then echo "nginx config validation failed. Run just setup-nginx to regenerate config."; exit 1; fi; if sudo systemctl is-active --quiet nginx; then sudo systemctl reload nginx; else sudo systemctl enable --now nginx; fi; npm run frontend:build; FANIC_GUNICORN_WORKERS=1 bash scripts/start-gunicorn.sh

# Start nginx only (reload if already running).
start-nginx:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found. Run just setup-nginx first."; exit 1; fi; sudo nginx -t; if sudo systemctl is-active --quiet nginx; then sudo systemctl reload nginx; else sudo systemctl enable --now nginx; fi

# Stop nginx if running.
stop-nginx:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found"; exit 0; fi; if ! sudo systemctl is-active --quiet nginx; then echo "nginx is not running"; exit 0; fi; sudo systemctl stop nginx

# Show health/status of nginx and unix-socket gunicorn endpoints.
health:
    nginx_port=8080; fanic_socket="/run/fanic/fanic.sock"; moderation_socket="/run/fanic/fanic-moderation.sock"; if command -v nginx >/dev/null 2>&1; then nginx_installed=true; else nginx_installed=false; fi; if pgrep -x nginx >/dev/null 2>&1; then nginx_process=true; else nginx_process=false; fi; if ss -ltn "( sport = :${nginx_port} )" 2>/dev/null | grep -q LISTEN; then nginx_listening=true; else nginx_listening=false; fi; if [ -S "${fanic_socket}" ]; then fanic_socket_present=true; else fanic_socket_present=false; fi; if [ -S "${moderation_socket}" ]; then moderation_socket_present=true; else moderation_socket_present=false; fi; if curl -fsS "http://127.0.0.1:${nginx_port}/" >/dev/null 2>&1; then nginx_http=ok; else nginx_http=down; fi; if [ "${fanic_socket_present}" = true ] && curl -fsS --unix-socket "${fanic_socket}" "http://localhost/" >/dev/null 2>&1; then fanic_socket_http=ok; else fanic_socket_http=down; fi; if [ "${moderation_socket_present}" = true ] && curl -fsS --unix-socket "${moderation_socket}" "http://localhost/health" >/dev/null 2>&1; then moderation_socket_http=ok; else moderation_socket_http=down; fi; if sudo systemctl cat fanic >/dev/null 2>&1; then fanic_service_installed=true; else fanic_service_installed=false; fi; if sudo systemctl cat fanic-moderation >/dev/null 2>&1; then moderation_service_installed=true; else moderation_service_installed=false; fi; if [ "${fanic_service_installed}" = true ] && sudo systemctl is-active --quiet fanic; then fanic_service_active=true; else fanic_service_active=false; fi; if [ "${moderation_service_installed}" = true ] && sudo systemctl is-active --quiet fanic-moderation; then moderation_service_active=true; else moderation_service_active=false; fi; echo "nginx installed : ${nginx_installed}"; echo "nginx process   : ${nginx_process}"; echo "nginx listening : ${nginx_listening} (127.0.0.1:${nginx_port})"; echo "nginx http      : ${nginx_http}"; echo "fanic socket    : ${fanic_socket_present} (${fanic_socket})"; echo "fanic socket http: ${fanic_socket_http}"; echo "moderation socket: ${moderation_socket_present} (${moderation_socket})"; echo "moderation socket http: ${moderation_socket_http}"; echo "fanic service   : installed=${fanic_service_installed} active=${fanic_service_active}"; echo "moderation svc  : installed=${moderation_service_installed} active=${moderation_service_active}"

# Stop the WSGI app (fanic systemd service) if running.
stop:
    if ! sudo systemctl cat fanic >/dev/null 2>&1; then echo "fanic.service is not installed"; exit 1; fi; if ! sudo systemctl is-active --quiet fanic; then echo "fanic.service is not running"; exit 0; fi; sudo systemctl stop fanic

# Restart the WSGI app (fanic systemd service).
restart:
    if ! sudo systemctl cat fanic >/dev/null 2>&1; then echo "fanic.service is not installed"; exit 1; fi; npm run frontend:build; sudo bash scripts/set-source-permissions.sh /opt/fanic/src /opt/fanic/frontend; sudo install -m 0644 scripts/fanic.service /etc/systemd/system/fanic.service; sudo install -m 0644 scripts/fanic-moderation.service /etc/systemd/system/fanic-moderation.service; sudo systemctl daemon-reload; sudo systemctl restart fanic-moderation fanic

# Normalize source file permissions so the fanic service user can read all app code.
set-permissions root_dir="/opt/fanic/src":
    sudo bash scripts/set-source-permissions.sh "{{ root_dir }}"

# Rebuild stored comic and fanart thumbnails using current settings.
# Usage examples:
#   just rebuild-thumbnails
#   just rebuild-thumbnails --dry-run

# just rebuild-thumbnails --scope comics
rebuild-thumbnails *args:
    uv run scripts/rebuild-thumbnails.py {{ args }}

# Build frontend TypeScript into static JavaScript assets.
_frontend-build:
    npm run frontend:build

# Build frontend TypeScript with source maps for local debugging.
_frontend-build-dev:
    npm run frontend:build:dev

# Type-check frontend TypeScript without emitting files.
_frontend-typecheck:
    npm run frontend:typecheck

# Lint frontend TypeScript.
_frontend-lint:
    npm run frontend:lint

# Check frontend TypeScript formatting.
_frontend-format-check:
    npm run frontend:format:check

# Format frontend TypeScript files in place.
_frontend-format:
    npm run frontend:format

# Watch and recompile frontend TypeScript on file changes.
_frontend-watch:
    npm run frontend:watch

# Frontend command router.
# Usage examples:
#   just frontend build
#   just frontend lint

# just frontend format-check
frontend action="build":
    action="{{ action }}"; if [ "$action" = "build" ]; then just _frontend-build; elif [ "$action" = "build-dev" ]; then just _frontend-build-dev; elif [ "$action" = "typecheck" ]; then just _frontend-typecheck; elif [ "$action" = "lint" ]; then just _frontend-lint; elif [ "$action" = "format-check" ]; then just _frontend-format-check; elif [ "$action" = "format" ]; then just _frontend-format; elif [ "$action" = "watch" ]; then just _frontend-watch; else echo "Unknown frontend action: $action"; echo "Allowed: build, build-dev, typecheck, lint, format-check, format, watch"; exit 1; fi

# Apply generated AO3 SQL into the Fanic SQLite database.
# Usage examples:
#   just apply-ao3tags-sql

# just apply-ao3tags-sql ./logs/ao3_tags_dump.fanic.upsert.sql
apply-ao3tags-sql sql_path="./logs/ao3_tags_dump.fanic.upsert.sql":
    uv run python -c "from pathlib import Path; import sqlite3; from fanic.settings import DB_PATH; raw = r'{{ sql_path }}'; normalized = raw.split('=', 1)[1] if raw.startswith('sql_path=') else raw; sql_file = Path(normalized).expanduser().resolve(); conn = sqlite3.connect(DB_PATH); conn.executescript(sql_file.read_text(encoding='utf-8')); conn.commit(); conn.close(); print(f'Applied SQL from {sql_file} to {DB_PATH}')"

# Apply a transferred AO3 SQL file on this server (apply-only workflow).
# Usage examples:
#   just import-ao3tags-from-file-and-apply

# just import-ao3tags-from-file-and-apply ./logs/ao3_freeform_tags.fanic.upsert.sql
import-ao3tags-from-file-and-apply sql_path="./logs/ao3_freeform_tags.fanic.upsert.sql":
    just apply-ao3tags-sql "{{ sql_path }}"

# Convert a local AO3 CSV dump into Fanic import files.
# Usage examples:
#   just wrangle-ao3-dump

# just wrangle-ao3-dump ./tmp/ao3tags-live/tags-20210226.csv 10
wrangle-ao3-dump source_path="./tmp/ao3tags-live/tags-20210226.csv" min_count="1":
    uv run scripts/export_ao3tags_for_fanic.py --source "{{ source_path }}" --min-count {{ min_count }} --out-dir logs

# Print top tags by effective popularity (seed_count + usage_count).
# Usage examples:
#   just report-tag-popularity

# just report-tag-popularity 100 freeform hurt
report-tag-popularity limit="50" tag_type="" query="":
    uv run src/fanic/main.py report-tag-popularity --limit {{ limit }} --type "{{ tag_type }}" --q "{{ query }}"

# One-shot backfill: usage_count = current number of work_tags rows per tag.
backfill-tag-popularity:
    uv run src/fanic/main.py backfill-tag-popularity
