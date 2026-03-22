from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Final
from typing import cast
from wsgiref.types import WSGIApplication

import cylinder
import waitress

from fanic.db import initialize_database
from fanic.moderation import initialize_moderation_models
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parent
CYLINDER_SITES_DIR: Final[Path] = PACKAGE_ROOT / "cylinder_sites"
SITE_NAME: Final[str] = "fanicsite"
OK = 0


def _resolve_log_path(template: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved = template.replace("%TIMESTAMP%", timestamp).strip()
    value = resolved if resolved else f"logs/{timestamp}.log"
    path = Path(value).expanduser().resolve()
    if path.suffix:
        return path
    return path.with_suffix(".log")


def _build_cylinder_log_handler() -> logging.FileHandler:
    settings = get_settings()
    log_path = _resolve_log_path(settings.log_path_template)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return logging.FileHandler(log_path, encoding="utf-8")


def startup() -> None:
    ensure_storage_dirs()
    initialize_database()
    _ = initialize_moderation_models()


def app_map() -> tuple[str, str, dict[str, object]]:
    return str(CYLINDER_SITES_DIR), SITE_NAME, {}


def create_app() -> WSGIApplication:
    startup()
    log_handler = _build_cylinder_log_handler()
    return cast(
        WSGIApplication,
        cylinder.get_app(  # pyright: ignore[reportUnknownMemberType]
            app_map,
            log_level=logging.DEBUG,
            log_handler=log_handler,
        ),
    )


def serve(host: str, port: int) -> int:
    app = create_app()
    try:
        waitress.serve(app, host=host, port=port)
    except KeyboardInterrupt:
        print("Shutting down gracefully...", flush=True)
    return OK
