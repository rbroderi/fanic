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
    uv run pytest --cov=src/fanic --cov-report=term-missing {{ args }}
