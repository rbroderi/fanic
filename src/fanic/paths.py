from __future__ import annotations

from pathlib import Path

from fanic.settings import get_settings

PACKAGE_ROOT = Path(__file__).resolve().parent
_SETTINGS = get_settings()
DATA_ROOT = _SETTINGS.data_root
DB_PATH = DATA_ROOT / "fanic.db"
CBZ_DIR = DATA_ROOT / "cbz"
WORKS_DIR = DATA_ROOT / "works"


def ensure_storage_dirs() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    CBZ_DIR.mkdir(parents=True, exist_ok=True)
    WORKS_DIR.mkdir(parents=True, exist_ok=True)
