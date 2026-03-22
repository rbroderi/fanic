set shell := ["powershell.exe", "-NoLogo", "-Command"]

_default:
    @just --list

# Initialize the SQLite database schema.
init-db:
    uv run src\fanic\main.py init-db

# Launch the local development server.
serve:
    $port = 8000; $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if ($listeners) { $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force -ErrorAction Stop } catch {} } }; uv run src\fanic\main.py serve --host 127.0.0.1 --port 8000

# Run autopep695 in check or format mode.
autopep695 mode="check":
    if (("{{ mode }}" -ne "check") -and ("{{ mode }}" -ne "format")) { throw "mode must be 'check' or 'format'" }; uv run autopep695 {{ mode }} src

# Backward-compatible alias for check mode.
autopep695-check:
    just autopep695 check
