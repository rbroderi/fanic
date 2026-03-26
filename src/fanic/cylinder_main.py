from __future__ import annotations

import hashlib
import hmac
import logging
import signal
import sys
import time
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from collections.abc import Callable
from collections.abc import Iterable
from datetime import datetime
from html import escape
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Final
from typing import cast
from urllib.parse import parse_qs
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
ALPHA_INVITE_COOKIE_NAME: Final[str] = "fanic_alpha_access"
ALPHA_INVITE_PATH: Final[str] = "/__alpha_invite"
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


def _decode_alpha_access_cookie(token: str, secret: str) -> bool:
    value = token.strip()
    if not value:
        return False

    parts = value.split(".", maxsplit=1)
    if len(parts) != 2:
        return False

    payload_b64, provided_sig = parts
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        return False

    padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload_text = urlsafe_b64decode(padded_payload.encode("utf-8")).decode("utf-8")
        expires_at = int(payload_text)
    except (ValueError, UnicodeDecodeError):
        return False
    return expires_at >= int(time.time())


def _encode_alpha_access_cookie(secret: str, max_age: int) -> str:
    expires_at = int(time.time()) + max_age
    payload_b64 = (
        urlsafe_b64encode(str(expires_at).encode("utf-8")).decode("utf-8").rstrip("=")
    )
    signature = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"


def _read_form_body(environ: dict[str, object]) -> dict[str, str]:
    content_length_obj = environ.get("CONTENT_LENGTH", "")
    try:
        content_length = int(str(content_length_obj).strip())
    except ValueError:
        content_length = 0
    if content_length <= 0:
        return {}

    stream_obj = environ.get("wsgi.input")
    if stream_obj is None or not hasattr(stream_obj, "read"):
        return {}

    read_fn = cast(Callable[[int], bytes], getattr(stream_obj, "read"))
    raw_body = read_fn(content_length)
    parsed = parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _invite_page_response(
    start_response: Callable[..., object],
    *,
    next_url: str,
    error_message: str,
    status: str = "200 OK",
) -> list[bytes]:
    safe_next_url = escape(next_url)
    error_html = (
        f'<p style="color:#b00020; margin:0 0 0.85rem 0;">{escape(error_message)}</p>'
        if error_message
        else ""
    )
    body_text = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Alpha Access Required</title></head>"
        '<body style="font-family:Arial,sans-serif;background:#f7f7f8;margin:0;padding:2rem;">'
        '<main style="max-width:460px;margin:10vh auto;background:#fff;padding:1.2rem;'
        'border:1px solid #ddd;border-radius:8px;">'
        '<h1 style="margin-top:0;">Private Alpha</h1>'
        '<p style="margin-top:0;">Enter your invite code to continue.</p>'
        f"{error_html}"
        f'<form method="post" action="{ALPHA_INVITE_PATH}">'
        f'<input type="hidden" name="next" value="{safe_next_url}">'
        '<label for="inviteCode">Invite code</label>'
        '<input id="inviteCode" name="invite_code" type="password" required '
        'style="display:block;width:100%;margin:.45rem 0 1rem;padding:.55rem;">'
        '<button type="submit" style="padding:.55rem .95rem;">Unlock</button>'
        "</form></main></body></html>"
    )
    body = body_text.encode("utf-8")
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]
    start_response(status, headers)
    return [body]


def _alpha_invite_gate_middleware(app: WSGIApplication) -> WSGIApplication:
    settings = get_settings()
    if not settings.alpha_invite_gate_enabled:
        return app

    invite_codes = settings.alpha_invite_codes

    secret = settings.session_secret
    cookie_max_age = settings.alpha_invite_cookie_max_age
    cookie_samesite = settings.session_cookie_samesite
    secure_cookie = settings.session_secure_effective

    def gated_app(
        environ: dict[str, object],
        start_response: Callable[..., object],
    ) -> Iterable[bytes]:
        token = _cookie_value(environ, ALPHA_INVITE_COOKIE_NAME)
        has_access = _decode_alpha_access_cookie(token, secret)
        if has_access:
            return app(environ, start_response)

        path = str(environ.get("PATH_INFO", "")).strip()
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        query_string = str(environ.get("QUERY_STRING", "")).strip()
        requested_url = f"{path}?{query_string}" if query_string else path
        next_url = requested_url if requested_url else "/"

        if path == ALPHA_INVITE_PATH and method == "POST":
            form = _read_form_body(environ)
            invite_code = form.get("invite_code", "").strip()
            next_value = form.get("next", "").strip()
            redirect_target = next_value if next_value.startswith("/") else "/"
            if invite_code in invite_codes:
                cookie_value = _encode_alpha_access_cookie(secret, cookie_max_age)
                body = b"See Other"
                set_cookie = (
                    f"{ALPHA_INVITE_COOKIE_NAME}={cookie_value}; "
                    f"Max-Age={cookie_max_age}; Path=/; HttpOnly; SameSite={cookie_samesite}"
                )
                if secure_cookie:
                    set_cookie += "; Secure"
                headers = [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    ("Location", redirect_target),
                    ("Set-Cookie", set_cookie),
                ]
                start_response("303 See Other", headers)
                return [body]
            return _invite_page_response(
                start_response,
                next_url=redirect_target,
                error_message="Invalid invite code.",
                status="403 Forbidden",
            )

        return _invite_page_response(
            start_response, next_url=next_url, error_message=""
        )

    return gated_app


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
    return _security_headers_middleware(
        _alpha_invite_gate_middleware(_admin_path_guard(raw_app))
    )


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
