set shell := ["powershell.exe", "-NoLogo", "-Command"]

_default:
    @just --list

# Initialize the SQLite database schema.
init-db:
    uv run fanic init-db

# Launch the local development server.
serve:
    $port = 8000; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} } }; uv run python -m fanic serve --host 127.0.0.1 --port 8000
