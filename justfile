set shell := ["powershell.exe", "-NoLogo", "-Command"]

_default:
    @just --list

# Initialize the SQLite database schema.
init-db:
    uv run src\fanic\main.py init-db

# Launch the local development server.
serve:
    trap [System.Management.Automation.PipelineStoppedException] { Write-Host "Shutting down gracefully..."; exit 0 }; $port = 8000; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} } }; uv run src\fanic\main.py serve --host 127.0.0.1 --port 8000; $code = $LASTEXITCODE; if (($code -ne 0) -and ($code -ne 130) -and ($code -ne -1073741510) -and ($code -ne 3221225786)) { Write-Host "serve exited with code $code (suppressed for dev serve workflow)" }; exit 0

# Run autopep695 in check or format mode.
autopep695 mode="check":
    if (("{{ mode }}" -ne "check") -and ("{{ mode }}" -ne "format")) { throw "mode must be 'check' or 'format'" }; uv run autopep695 {{ mode }} src

# Run pytest with coverage for the src package.
test-cov *args:
    $env:FANIC_ENABLE_BEARTYPE = "1"; uv run pytest --cov=src/fanic --cov-report=term-missing {{ args }}

# Install and configure nginx on Windows for FANIC.
setup-nginx-windows:
    powershell -NoLogo -ExecutionPolicy Bypass -File scripts\setup-nginx-windows.ps1

# Start nginx (or reload if already running) and then run the WSGI server.
start:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { throw "nginx.exe not found at C:\nginx\nginx.exe. Run 'just setup-nginx-windows' first." }; $nginxPrefix = "C:/nginx/"; & $nginxExe -t -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx config validation failed. Run 'just setup-nginx-windows' to regenerate config." }; $running = Get-Process nginx -ErrorAction SilentlyContinue; if ($running) { & $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx reload failed" } } else { $null = Start-Process -FilePath $nginxExe -ArgumentList @("-p", $nginxPrefix, "-c", "conf/nginx.conf") -WindowStyle Hidden -PassThru; Start-Sleep -Milliseconds 800; $started = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $started) { throw "nginx did not start" } }; just serve

# Start nginx only (reload if already running).
start-nginx:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { throw "nginx.exe not found at C:\nginx\nginx.exe. Run 'just setup-nginx-windows' first." }; $nginxPrefix = "C:/nginx/"; & $nginxExe -t -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx config validation failed. Run 'just setup-nginx-windows' to regenerate config." }; $running = Get-Process nginx -ErrorAction SilentlyContinue; if ($running) { & $nginxExe -s reload -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx reload failed" } } else { $null = Start-Process -FilePath $nginxExe -ArgumentList @("-p", $nginxPrefix, "-c", "conf/nginx.conf") -WindowStyle Hidden -PassThru; Start-Sleep -Milliseconds 800; $started = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $started) { throw "nginx did not start" } }

# Stop nginx if running.
stop-nginx:
    $nginxExe = "C:\nginx\nginx.exe"; if (-not (Test-Path $nginxExe)) { Write-Host "nginx.exe not found at C:\nginx\nginx.exe"; exit 0 }; $nginxPrefix = "C:/nginx/"; $running = Get-Process nginx -ErrorAction SilentlyContinue; if (-not $running) { Write-Host "nginx is not running"; exit 0 }; & $nginxExe -s stop -p $nginxPrefix -c conf/nginx.conf; if ($LASTEXITCODE -ne 0) { throw "nginx stop failed" }

# Show health/status of nginx and WSGI endpoints.
health:
    $nginxExe = "C:\nginx\nginx.exe"; $nginxPort = 8080; $wsgiPort = 8000; $nginxInstalled = Test-Path $nginxExe; $nginxProcess = Get-Process nginx -ErrorAction SilentlyContinue; $nginxListening = Get-NetTCPConnection -LocalPort $nginxPort -State Listen -ErrorAction SilentlyContinue; $wsgiListening = Get-NetTCPConnection -LocalPort $wsgiPort -State Listen -ErrorAction SilentlyContinue; $nginxHttp = $null; try { $nginxHttp = Invoke-WebRequest -Uri "http://127.0.0.1:$nginxPort/" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop } catch { $nginxHttp = $null }; $wsgiHttp = $null; try { $wsgiHttp = Invoke-WebRequest -Uri "http://127.0.0.1:$wsgiPort/" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop } catch { $wsgiHttp = $null }; Write-Host "nginx installed : $nginxInstalled"; Write-Host "nginx process   : $([bool]$nginxProcess)"; Write-Host "nginx listening : $([bool]$nginxListening) (127.0.0.1:$nginxPort)"; if ($nginxHttp) { Write-Host "nginx http      : ok (status $($nginxHttp.StatusCode))" } else { Write-Host "nginx http      : down" }; Write-Host "wsgi listening  : $([bool]$wsgiListening) (127.0.0.1:$wsgiPort)"; if ($wsgiHttp) { Write-Host "wsgi http       : ok (status $($wsgiHttp.StatusCode))" } else { Write-Host "wsgi http       : down" }
