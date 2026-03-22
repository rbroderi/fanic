from __future__ import annotations

from pathlib import Path
from typing import Final
from typing import cast
from wsgiref.types import WSGIApplication

import cylinder
import waitress

from fanic.db import initialize_database
from fanic.paths import ensure_storage_dirs

PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parent
CYLINDER_SITES_DIR: Final[Path] = PACKAGE_ROOT / "cylinder_sites"
SITE_NAME: Final[str] = "fanicsite"


def startup() -> None:
    ensure_storage_dirs()
    initialize_database()


def app_map() -> tuple[str, str, dict[str, object]]:
    return str(CYLINDER_SITES_DIR), SITE_NAME, {}


def create_app() -> WSGIApplication:
    startup()
    return cast(WSGIApplication, cylinder.get_app(app_map))  # pyright: ignore[reportUnknownMemberType]


def serve(host: str, port: int) -> None:
    app = create_app()
    waitress.serve(app, host=host, port=port)
