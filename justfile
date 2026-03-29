set shell := ["bash", "-lc"]
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

_default:
    @just --list

# Initialize the SQLite database schema.
[windows]
init-db:
    uv run src\fanic\main.py init-db

[unix]
init-db:
    uv run src/fanic/main.py init-db

# Launch the local development server.
[windows]
serve:
    trap [System.Management.Automation.PipelineStoppedException] { Write-Host "Shutting down gracefully..."; exit 0 }; $port = 8000; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} } }; uv run src\fanic\main.py serve --host 127.0.0.1 --port 8000; $code = $LASTEXITCODE; if (($code -ne 0) -and ($code -ne 130) -and ($code -ne -1073741510) -and ($code -ne 3221225786)) { Write-Host "serve exited with code $code (suppressed for dev serve workflow)" }; exit 0

[unix]
serve:
    uv run src/fanic/main.py serve --host 127.0.0.1 --port 8000; code=$?; if [ $code -ne 0 ] && [ $code -ne 130 ]; then echo "serve exited with code $code (suppressed for dev serve workflow)"; fi; exit 0

# Run autopep695 in check or format mode.
[windows]
autopep695 mode="check":
    if (("{{ mode }}" -ne "check") -and ("{{ mode }}" -ne "format")) { throw "mode must be 'check' or 'format'" }; uv run autopep695 {{ mode }} src

[unix]
autopep695 mode="check":
    mode="{{ mode }}"; if [ "$mode" != "check" ] && [ "$mode" != "format" ]; then echo "mode must be 'check' or 'format'"; exit 1; fi; uv run autopep695 "$mode" src

# Run the same Ruff checks as the GitHub workflow.
ruff-ci:
    uvx ruff check --exclude typings src tests; uvx ruff format --check --exclude typings src tests

# Run Ruff in pre-commit mode (auto-format, then lint check).
ruff-precommit:
    uvx ruff format --exclude typings src tests; uvx ruff check --exclude typings src tests

# Install prek pre-commit hook and hook environments.
prek-install:
    uvx prek install --overwrite --install-hooks

# Run prek hooks against all files.
prek-run:
    uvx prek run --all-files

# Run pytest with coverage for the src package.
[windows]
test-cov *args:
    $env:FANIC_ENABLE_BEARTYPE = "1"; uv run pytest --cov=src/fanic --cov-report=term-missing {{ args }}

[unix]
test-cov *args:
    if sudo systemctl cat fanic >/dev/null 2>&1 && sudo systemctl is-active --quiet fanic; then sudo systemctl stop fanic; fi; args='{{ args }}'; if [ -n "$args" ]; then FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-report=term-missing {{ args }}; else FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-report= --ignore=tests/test_moderation_media.py && FANIC_ENABLE_BEARTYPE=1 uv run pytest --cov=src/fanic --cov-append --cov-report=term-missing tests/test_moderation_media.py; fi

# Install and configure nginx on Windows for FANIC.
[windows]
setup-nginx-windows:
    powershell -NoLogo -ExecutionPolicy Bypass -File scripts\setup-nginx-windows.ps1

[unix]
setup-nginx-windows:
    echo "setup-nginx-windows is only supported on Windows"; exit 1

# Install and configure nginx on Ubuntu for FANIC.
[windows]
setup-nginx-linux:
    echo "setup-nginx-linux is only supported on Linux"; exit 1

[unix]
setup-nginx-linux:
    bash scripts/setup-nginx-ubuntu.sh

# Relocate storage root, update .env FANIC_DATA_DIR, and refresh nginx aliases.
[windows]
relocate-storage target:
    powershell -NoLogo -ExecutionPolicy Bypass -File scripts\relocate-storage-windows.ps1 -TargetStorageRoot "{{ target }}"

[unix]
relocate-storage target:
    bash scripts/relocate-storage-ubuntu.sh --target-storage-root "{{ target }}"

# Start nginx (or reload if already running) and then run the WSGI server.
[windows]
start:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { throw "nginx.exe not found at C:\nginx\nginx.exe. Run 'just setup-nginx-windows' first." }; $nginxPrefix = "C:/nginx/"; & $nginxExe -t -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx config validation failed. Run 'just setup-nginx-windows' to regenerate config." }; $running = Get-Process nginx -ErrorAction SilentlyContinue; if ($running) { & $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx reload failed" } } else { $null = Start-Process -FilePath $nginxExe -ArgumentList @("-p", $nginxPrefix, "-c", "conf/nginx.conf") -WindowStyle Hidden -PassThru; Start-Sleep -Milliseconds 800; $started = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $started) { throw "nginx did not start" } }; just serve

[unix]
start:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found. Run just setup-nginx-linux first."; exit 1; fi; if ! sudo nginx -t; then echo "nginx config validation failed. Run just setup-nginx-linux to regenerate config."; exit 1; fi; if sudo systemctl is-active --quiet nginx; then sudo systemctl reload nginx; else sudo systemctl enable --now nginx; fi; uv run src/fanic/main.py serve --host 127.0.0.1 --port 8000; code=$?; if [ $code -ne 0 ] && [ $code -ne 130 ]; then echo "serve exited with code $code (suppressed for dev serve workflow)"; fi; exit 0

# Start nginx only (reload if already running).
[windows]
start-nginx:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { throw "nginx.exe not found at C:\nginx\nginx.exe. Run 'just setup-nginx-windows' first." }; $nginxPrefix = "C:/nginx/"; & $nginxExe -t -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx config validation failed. Run 'just setup-nginx-windows' to regenerate config." }; $running = Get-Process nginx -ErrorAction SilentlyContinue; if ($running) { & $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx reload failed" } } else { $null = Start-Process -FilePath $nginxExe -ArgumentList @("-p", $nginxPrefix, "-c", "conf/nginx.conf") -WindowStyle Hidden -PassThru; Start-Sleep -Milliseconds 800; $started = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $started) { throw "nginx did not start" } }

[unix]
start-nginx:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found. Run just setup-nginx-linux first."; exit 1; fi; sudo nginx -t; if sudo systemctl is-active --quiet nginx; then sudo systemctl reload nginx; else sudo systemctl enable --now nginx; fi

# Stop nginx if running.
[windows]
stop-nginx:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { Write-Host "nginx.exe not found at C:\nginx\nginx.exe"; exit 0 }; $nginxPrefix = "C:/nginx/"; $running = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $running) { Write-Host "nginx is not running"; exit 0 }; & $nginxExe -s stop -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx stop failed" }

[unix]
stop-nginx:
    if ! command -v nginx >/dev/null 2>&1; then echo "nginx not found"; exit 0; fi; if ! sudo systemctl is-active --quiet nginx; then echo "nginx is not running"; exit 0; fi; sudo systemctl stop nginx

# Show health/status of nginx and WSGI endpoints.
[windows]
health:
    $nginxExe = "C:\nginx\nginx.exe"; $nginxPort = 8080; $wsgiPort = 8000; $nginxInstalled = Test-Path $nginxExe; $nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue; $nginxListening = Get-NetTCPConnection -LocalPort $nginxPort -State Listen -ErrorAction SilentlyContinue; $wsgiListening = Get-NetTCPConnection -LocalPort $wsgiPort -State Listen -ErrorAction SilentlyContinue; $nginxHttp = $null; try { $nginxHttp = Invoke-WebRequest -Uri "http://127.0.0.1:$nginxPort/" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop } catch { $nginxHttp = $null }; $wsgiHttp = $null; try { $wsgiHttp = Invoke-WebRequest -Uri "http://127.0.0.1:$wsgiPort/" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop } catch { $wsgiHttp = $null }; Write-Host "nginx installed : $nginxInstalled"; Write-Host "nginx process   : $([bool]$nginxProcess)"; Write-Host "nginx listening : $([bool]$nginxListening) (127.0.0.1:$nginxPort)"; if ($nginxHttp) { Write-Host "nginx http      : ok (status $($nginxHttp.StatusCode))" } else { Write-Host "nginx http      : down" }; Write-Host "wsgi listening  : $([bool]$wsgiListening) (127.0.0.1:$wsgiPort)"; if ($wsgiHttp) { Write-Host "wsgi http       : ok (status $($wsgiHttp.StatusCode))" } else { Write-Host "wsgi http       : down" }

[unix]
health:
    nginx_port=8080; wsgi_port=8000; if command -v nginx >/dev/null 2>&1; then nginx_installed=true; else nginx_installed=false; fi; if pgrep -x nginx >/dev/null 2>&1; then nginx_process=true; else nginx_process=false; fi; if ss -ltn "( sport = :${nginx_port} )" 2>/dev/null | grep -q LISTEN; then nginx_listening=true; else nginx_listening=false; fi; if ss -ltn "( sport = :${wsgi_port} )" 2>/dev/null | grep -q LISTEN; then wsgi_listening=true; else wsgi_listening=false; fi; if curl -fsS "http://127.0.0.1:${nginx_port}/" >/dev/null 2>&1; then nginx_http=ok; else nginx_http=down; fi; if curl -fsS "http://127.0.0.1:${wsgi_port}/" >/dev/null 2>&1; then wsgi_http=ok; else wsgi_http=down; fi; echo "nginx installed : ${nginx_installed}"; echo "nginx process   : ${nginx_process}"; echo "nginx listening : ${nginx_listening} (127.0.0.1:${nginx_port})"; echo "nginx http      : ${nginx_http}"; echo "wsgi listening  : ${wsgi_listening} (127.0.0.1:${wsgi_port})"; echo "wsgi http       : ${wsgi_http}"

# Stop the WSGI app (fanic systemd service) if running.
[windows]
stop:
    echo "stop is only supported on Linux systemd deployments"; exit 1

[unix]
stop:
    if ! sudo systemctl cat fanic >/dev/null 2>&1; then echo "fanic.service is not installed"; exit 1; fi; if ! sudo systemctl is-active --quiet fanic; then echo "fanic.service is not running"; exit 0; fi; sudo systemctl stop fanic

# Restart the WSGI app (fanic systemd service).
[windows]
restart:
    echo "restart is only supported on Linux systemd deployments"; exit 1

[unix]
restart:
    if ! sudo systemctl cat fanic >/dev/null 2>&1; then echo "fanic.service is not installed"; exit 1; fi; sudo systemctl daemon-reload; sudo systemctl restart fanic

# Normalize source file permissions so the fanic service user can read all app code.
[windows]
set-permissions root_dir="/opt/fanic/src":
    echo "set-permissions is only supported on Linux"; exit 1

[unix]
set-permissions root_dir="/opt/fanic/src":
    sudo bash scripts/set-source-permissions.sh "{{ root_dir }}"
