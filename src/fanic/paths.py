from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("FANIC_DATA_DIR", PACKAGE_ROOT / "storage"))
DB_PATH = DATA_ROOT / "fanic.db"
CBZ_DIR = DATA_ROOT / "cbz"
WORKS_DIR = DATA_ROOT / "works"


def ensure_storage_dirs() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    CBZ_DIR.mkdir(parents=True, exist_ok=True)
    WORKS_DIR.mkdir(parents=True, exist_ok=True)
