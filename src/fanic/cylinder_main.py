from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable
from collections.abc import Iterable
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Final
from typing import cast
from wsgiref.types import WSGIApplication

import cylinder
import waitress

from fanic.cylinder_sites.common import SESSION_COOKIE_NAME
from fanic.cylinder_sites.common import decode_session
from fanic.db import initialize_database
from fanic.moderation import initialize_moderation_models
from fanic.repository import get_user_role
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parent
CYLINDER_SITES_DIR: Final[Path] = PACKAGE_ROOT / "cylinder_sites"
SITE_NAME: Final[str] = "fanicsite"
ADMIN_ROLES: Final[set[str]] = {"superadmin", "admin"}
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
    settings = get_settings()
    settings.validate_production_settings()
    ensure_storage_dirs()
    initialize_database()
    _ = initialize_moderation_models()


def app_map() -> tuple[str, str, dict[str, object]]:
    return str(CYLINDER_SITES_DIR), SITE_NAME, {}


def _cookie_value(environ: dict[str, object], cookie_name: str) -> str:
    cookie_header = str(environ.get("HTTP_COOKIE", "")).strip()
    if not cookie_header:
        return ""

    parsed_cookie: SimpleCookie[str] = SimpleCookie()
    parsed_cookie.load(cookie_header)
    morsel = parsed_cookie.get(cookie_name)
    if morsel is None:
        return ""
    return str(morsel.value).strip()


def _is_authorized_admin_request(environ: dict[str, object]) -> bool:
    path = str(environ.get("PATH_INFO", "")).strip()
    if not path.startswith("/admin/"):
        return True

    token = _cookie_value(environ, SESSION_COOKIE_NAME)
    if not token:
        return False

    username = decode_session(token)
    role = get_user_role(username)
    return role in ADMIN_ROLES


def _admin_path_guard(app: WSGIApplication) -> WSGIApplication:
    def guarded_app(
        environ: dict[str, object],
        start_response: Callable[..., object],
    ) -> Iterable[bytes]:
        if _is_authorized_admin_request(environ):
            return app(environ, start_response)

        body = b"Forbidden"
        headers = [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ]
        start_response("403 Forbidden", headers)
        return [body]

    return guarded_app


def _security_headers_middleware(app: WSGIApplication) -> WSGIApplication:
    settings = get_settings()
    add_hsts = settings.require_https_effective

    def secured_app(
        environ: dict[str, object],
        start_response: Callable[..., object],
    ) -> Iterable[bytes]:
        def injecting_start_response(
            status: str,
            headers: list[tuple[str, str]],
            exc_info: object = None,
        ) -> object:
            headers.extend(
                [
                    ("X-Content-Type-Options", "nosniff"),
                    ("X-Frame-Options", "DENY"),
                    ("Referrer-Policy", "strict-origin-when-cross-origin"),
                    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
                ]
            )
            if add_hsts:
                headers.append(
                    ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                )
            return start_response(status, headers, exc_info)

        return app(environ, injecting_start_response)

    return secured_app


def create_app() -> WSGIApplication:
    startup()
    log_handler = _build_cylinder_log_handler()
    raw_app = cast(
        WSGIApplication,
        cylinder.get_app(  # pyright: ignore[reportUnknownMemberType]
            app_map,
            log_level=logging.DEBUG,
            log_handler=log_handler,
        ),
    )
    return _security_headers_middleware(_admin_path_guard(raw_app))


def serve(host: str, port: int) -> int:
    settings = get_settings()
    app = create_app()

    def _shutdown_handler(signum: int, _frame: object) -> None:
        name = signal.Signals(signum).name
        print(f"Received {name}, shutting down gracefully...", flush=True)
        sys.exit(0)

    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown_handler)

    try:
        waitress.serve(
            app,
            host=host,
            port=port,
            threads=4,
            connection_limit=1000,
            recv_bytes=65536,
            channel_timeout=120,
            max_request_body_size=settings.max_cbz_upload_bytes + 1024 * 1024,
        )
    except KeyboardInterrupt:
        print("Shutting down gracefully...", flush=True)
    return OK
