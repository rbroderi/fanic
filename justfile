set shell := ["powershell.exe", "-NoLogo", "-Command"]

_default:
    @just --list

# Launch the local development server.
serve:
    $port = 8000; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} } }; uv run python -m co3 serve --host 127.0.0.1 --port 8000
