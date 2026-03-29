import hashlib
import hmac
import json
import logging
import mimetypes
import re
import secrets
import threading
import time
import tomllib
from collections.abc import Callable
from collections.abc import Iterable
from datetime import datetime
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol
from typing import cast
from typing import runtime_checkable

import structlog
from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.cylinder_sites.site_layout import site_header_parts_for_template
from fanic.ingest import ingest_cbz
from fanic.repository import UserRole
from fanic.repository import get_local_user
from fanic.repository import get_user_role
from fanic.repository import get_user_theme_preference
from fanic.settings import STATIC_ASSETS_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import get_settings

mimetypes.add_type("image/avif", ".avif")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = (PACKAGE_ROOT / "dynamic").resolve()
ASSET_ROOT = STATIC_ASSETS_DIR.resolve()
_SETTINGS = get_settings()

SESSION_COOKIE_NAME = "fanic_session"
CSRF_COOKIE_NAME = "fanic_csrf"
AUTH0_OAUTH_COOKIE_NAME = "fanic_auth0_oauth"
SESSION_SECRET = _SETTINGS.session_secret
SESSION_MAX_AGE = _SETTINGS.session_max_age
SESSION_COOKIE_SECURE = _SETTINGS.session_secure_effective
SESSION_COOKIE_SAMESITE = _SETTINGS.session_cookie_samesite
REQUIRE_HTTPS = _SETTINGS.require_https_effective
CSRF_PROTECT = _SETTINGS.csrf_protect_effective
MAX_CBZ_UPLOAD_BYTES = int(getattr(_SETTINGS, "max_cbz_upload_bytes", 268435456))
MAX_PAGE_UPLOAD_BYTES = int(getattr(_SETTINGS, "max_page_upload_bytes", 20971520))
AUTH0_OAUTH_MAX_AGE = 600
ALLOWED_CBZ_EXTENSIONS = set(getattr(_SETTINGS, "allowed_cbz_extensions", {".cbz"}))
ALLOWED_CBZ_CONTENT_TYPES = set(
    getattr(
        _SETTINGS,
        "allowed_cbz_content_types",
        {"application/zip", "application/x-cbz", "application/octet-stream"},
    )
)
ALLOWED_PAGE_EXTENSIONS = set(
    getattr(
        _SETTINGS,
        "allowed_page_extensions",
        {
            ".avif",
            ".bmp",
            ".gif",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        },
    )
)
ALLOWED_PAGE_CONTENT_TYPES = set(
    getattr(
        _SETTINGS,
        "allowed_page_content_types",
        {
            "image/avif",
            "image/bmp",
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
            "application/octet-stream",
        },
    )
)
ADMIN_USERNAME = _SETTINGS.admin_username
ADMIN_PASSWORD_HASH = _SETTINGS.admin_password_hash
AUTH_MAX_FAILURES = _SETTINGS.auth_max_failures
AUTH_WINDOW_SECONDS = _SETTINGS.auth_window_seconds
AUTH_LOCKOUT_SECONDS = _SETTINGS.auth_lockout_seconds
UPLOAD_RATE_WINDOW_SECONDS = int(getattr(_SETTINGS, "upload_rate_window_seconds", 60))
UPLOAD_RATE_MAX_REQUESTS = int(getattr(_SETTINGS, "upload_rate_max_requests", 20))
UPLOAD_MAX_CONCURRENT_PER_USER = int(getattr(_SETTINGS, "upload_max_concurrent_per_user", 2))
COMIC_INGEST_MAX_CONCURRENT = int(getattr(_SETTINGS, "comic_ingest_max_concurrent", 3))
COMIC_INGEST_QUEUE_WAIT_SECONDS = int(getattr(_SETTINGS, "comic_ingest_queue_wait_seconds", 180))

# Maximum length for user-supplied text form fields.
MAX_SHORT_FIELD_LENGTH = 512
MAX_LONG_FIELD_LENGTH = 4096
MAX_URL_FIELD_LENGTH = 2048

# Per-IP rate limiting for general POST endpoints (dmca, profile, etc.).
POST_RATE_WINDOW_SECONDS = 60
POST_RATE_MAX_REQUESTS = 30

_POST_FORM_OPEN_TAG_RE = re.compile(
    r"<form\\b[^>]*\\bmethod\\s*=\\s*(['\"]?)post\\1[^>]*>",
    flags=re.IGNORECASE,
)
_AUTH_LOCK = threading.Lock()
_AUTH_FAILURE_TIMESTAMPS: dict[str, list[float]] = {}
_AUTH_LOCKED_UNTIL: dict[str, float] = {}
_POST_RATE_LOCK = threading.Lock()
_POST_RATE_TIMESTAMPS: dict[str, list[float]] = {}
_UPLOAD_LOCK = threading.Lock()
_UPLOAD_ATTEMPT_TIMESTAMPS: dict[str, list[float]] = {}
_UPLOAD_IN_FLIGHT: dict[str, int] = {}
_COMIC_INGEST_LOCK = threading.Lock()
_COMIC_INGEST_CONDITION = threading.Condition(_COMIC_INGEST_LOCK)
_COMIC_INGEST_ACTIVE = 0
_COMIC_INGEST_WAITING = 0
_REQUEST_ID_ATTR = "_fanic_request_id"

_SENSITIVE_FIELD_NAMES = {
    "password",
    "pass",
    "passwd",
    "token",
    "csrf_token",
    "authorization",
    "cookie",
    "secret",
    "session",
    "admin_password_hash",
}

_structlog_configured = False

RATING_ICON_BY_NAME = {
    "General Audiences": "citrus.svg",
    "Teen And Up Audiences": "orange.svg",
    "Mature": "lime.svg",
    "Explicit": "lemon.svg",
}

SITE_FOOTER_HTML = (
    '<footer class="site-footer" role="contentinfo">'
    '<div class="site-footer-inner">'
    '<a class="site-footer-link" href="/terms">Terms and Conditions</a>'
    '<span class="site-footer-sep" aria-hidden="true"> | </span>'
    '<a class="site-footer-link" href="/faq">FAQ</a>'
    '<span class="site-footer-sep" aria-hidden="true"> | </span>'
    '<a class="site-footer-link" href="/dmca">Report Copyright/Content</a>'
    '<span class="site-footer-sep" aria-hidden="true"> | </span>'
    '<a class="site-footer-link" href="/cbz-format">CBZ SPEC INFO</a>'
    "</div>"
    "</footer>"
)

SITE_HEAD_ASSETS_HTML = (
    '<link rel="icon" href="/static/logo.png" type="image/png" />\n'
    '    <link rel="preconnect" href="https://fonts.googleapis.com" />\n'
    '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
    '    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Source+Serif+4:wght@400;700&display=swap" rel="stylesheet" />\n'
    '    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" />\n'
    '    <link rel="stylesheet" href="/static/styles.css" />'
)
SITE_COMMON_SCRIPTS_HTML = '<script src="/static/user-menu.js?v=20260329-logged-out-page"></script>'

THEME_VAR_ALLOWLIST = {
    "bg",
    "paper",
    "ink",
    "accent",
    "accent-soft",
    "line",
    "muted",
    "tag-bg",
    "panel-bg",
    "header-bg",
    "surface-strong",
    "danger-bg",
    "danger-line",
    "danger-ink",
    "reader-overlay-border",
    "reader-overlay-bg",
    "reader-overlay-ink",
    "reader-page-bg",
    "bg-glow-1",
    "bg-glow-2",
}
SAFE_THEME_VALUE_PATTERN = re.compile(r"^[#(),.%/\-\sA-Za-z0-9]+$")

JWTEncode = Callable[[object, object, object], bytes]
JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_ENCODE = cast(JWTEncode, jwt.encode)
JWT_DECODE = cast(JWTDecode, jwt.decode)


def _resolve_log_path(template: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    resolved = template.replace("%TIMESTAMP%", timestamp).strip()
    value = resolved if resolved else f"logs/{timestamp}.log"
    path = Path(value).expanduser().resolve()
    if path.suffix:
        return path
    return path.with_suffix(".log")


def _ensure_file_logging_handler(log_path: Path) -> None:
    root_logger = logging.getLogger()
    target_path = log_path.resolve()

    for handler in root_logger.handlers:
        if not isinstance(handler, logging.FileHandler):
            continue
        current_path = Path(handler.baseFilename).resolve()
        if current_path == target_path:
            return

    file_handler = logging.FileHandler(target_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(file_handler)
    if root_logger.level == logging.NOTSET or root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)


def _configure_structlog() -> None:
    global _structlog_configured
    if _structlog_configured:
        return

    log_path = _resolve_log_path(_SETTINGS.log_path_template)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_file_logging_handler(log_path)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    structlog.get_logger("fanic.http").info(
        "logging initialized",
        log_path=str(log_path),
    )
    _structlog_configured = True


_configure_structlog()
LOGGER = structlog.get_logger("fanic.http")


@runtime_checkable
class QueryArgsLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class FormLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class CookieMapLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class FileUploadLike(Protocol):
    filename: str | None

    def save(self, dst: str | Path) -> None: ...


@runtime_checkable
class FileMapLike(Protocol):
    def get(self, key: str) -> FileUploadLike | None: ...


@runtime_checkable
class RequestLike(Protocol):
    path: str
    method: str
    args: QueryArgsLike
    form: FormLike
    files: FileMapLike
    cookies: CookieMapLike


@runtime_checkable
class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...

    def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "Lax",
    ) -> None: ...

    def delete_cookie(self, key: str, path: str = "/") -> None: ...


def request_id(request: RequestLike, response: ResponseLike | None = None) -> str:
    existing = getattr(request, _REQUEST_ID_ATTR, "")
    existing_id = str(existing).strip()
    if existing_id:
        if response is not None:
            response.headers["X-Request-ID"] = existing_id
        return existing_id

    incoming = _header_value(request, "X-Request-ID").strip()
    resolved = incoming if incoming else secrets.token_hex(16)
    setattr(request, _REQUEST_ID_ATTR, resolved)
    if response is not None:
        response.headers["X-Request-ID"] = resolved
    return resolved


def _is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    return any(name in lowered for name in _SENSITIVE_FIELD_NAMES)


def _redact_object(value: object) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        dict_value = cast(dict[object, object], value)
        for raw_key, raw_value in dict_value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_object(raw_value)
        return result
    if isinstance(value, list):
        list_value = cast(list[object], value)
        return [_redact_object(item) for item in list_value]
    if isinstance(value, tuple):
        tuple_value = cast(tuple[object, ...], value)
        return tuple(_redact_object(item) for item in tuple_value)
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


def _items_object_to_dict(items_obj: object) -> dict[str, object]:
    pairs = cast(Iterable[tuple[object, object]], items_obj)
    return {str(key): value for key, value in pairs}


def request_context_for_log(request: RequestLike) -> dict[str, object]:
    context: dict[str, object] = {
        "request_id": request_id(request),
        "method": str(getattr(request, "method", "")),
        "path": str(getattr(request, "path", "")),
        "client_ip": _request_client_ip(request),
    }

    user = current_user(request)
    if user:
        context["user"] = user

    form_obj = getattr(request, "form", None)
    if form_obj is not None and hasattr(form_obj, "items"):
        items_fn = cast(Callable[[], object], form_obj.items)
        items_obj = items_fn()
        try:
            raw_form = _items_object_to_dict(items_obj)
            context["form"] = _redact_object(raw_form)
        except Exception:
            pass

    args_obj = getattr(request, "args", None)
    if args_obj is not None and hasattr(args_obj, "items"):
        items_fn = cast(Callable[[], object], args_obj.items)
        items_obj = items_fn()
        try:
            raw_args = _items_object_to_dict(items_obj)
            context["args"] = _redact_object(raw_args)
        except Exception:
            pass

    return context


def log_exception(
    request: RequestLike,
    *,
    code: str,
    exc: Exception,
    message: str,
    extra: dict[str, object] | None = None,
) -> None:
    event = request_context_for_log(request)
    event["error_code"] = code
    event["exception_type"] = type(exc).__name__
    if extra:
        event["extra"] = _redact_object(extra)
    LOGGER.exception(message, **event)


def is_admin_request(request: RequestLike) -> bool:
    role = current_user_role(request)
    return role in {"superadmin", "admin"}


def role_for_user(username: str | None) -> UserRole:
    return get_user_role(username)


def current_user_role(request: RequestLike) -> UserRole:
    username = current_user(request)
    return role_for_user(username)


def admin_aware_detail(
    request: RequestLike,
    *,
    public_detail: str,
    exc: Exception | None = None,
) -> str:
    if not is_admin_request(request):
        return public_detail
    if exc is None:
        return public_detail
    return str(exc) if str(exc) else public_detail


def stable_api_error(
    request: RequestLike,
    response: ResponseLike,
    *,
    error: str,
    public_detail: str,
    status_code: int,
    exc: Exception | None = None,
) -> ResponseLike:
    rid = request_id(request, response)
    detail = admin_aware_detail(request, public_detail=public_detail, exc=exc)
    return json_response(
        response,
        {
            "ok": False,
            "error": error,
            "detail": detail,
            "request_id": rid,
        },
        status_code,
    )


def path_parts(request: RequestLike) -> list[str]:
    return [segment for segment in request.path.split("/") if segment]


def route_tail(request: RequestLike, prefix_parts: list[str]) -> list[str] | None:
    parts = path_parts(request)
    if len(parts) < len(prefix_parts):
        return None
    if parts[: len(prefix_parts)] != prefix_parts:
        return None
    return parts[len(prefix_parts) :]


def json_response(response: ResponseLike, payload: dict[str, object], status_code: int = 200) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "application/json; charset=utf-8"
    response.set_data(json.dumps(payload, ensure_ascii=True))
    return response


def text_error(response: ResponseLike, message: str, status_code: int = 404) -> ResponseLike:
    response.status_code = status_code
    response.content_type = "text/plain; charset=utf-8"
    response.set_data(message)
    return response


def send_file(response: ResponseLike, path: Path, filename: str | None = None) -> ResponseLike:
    if not path.exists() or not path.is_file():
        return text_error(response, "Not found", 404)

    content_type, _ = mimetypes.guess_type(str(path))
    response.content_type = content_type if content_type else "application/octet-stream"
    response.set_data(path.read_bytes())

    if filename:
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response


def safe_static_path(rel_path: str) -> Path | None:
    candidate = (ASSET_ROOT / rel_path).resolve()
    try:
        _ = candidate.relative_to(ASSET_ROOT)
    except ValueError:
        return None
    return candidate


def _header_value(request: RequestLike, header_name: str) -> str:
    headers_obj = getattr(request, "headers", None)
    if headers_obj is None:
        return ""
    if not hasattr(headers_obj, "get"):
        return ""
    getter = cast(Callable[[str, str], object], headers_obj.get)
    value_obj = getter(header_name, "")
    return str(value_obj)


def _upload_filename(upload: FileUploadLike) -> str:
    filename_obj = getattr(upload, "filename", "")
    return str(filename_obj).strip()


def _upload_content_type(upload: FileUploadLike) -> str:
    content_type_obj = getattr(upload, "content_type", "")
    return str(content_type_obj).strip().lower()


def _extension_allowed(filename: str, allowed_extensions: set[str]) -> bool:
    if not filename:
        return False
    suffix = Path(filename).suffix.lower()
    return suffix in allowed_extensions


def _content_type_allowed(content_type: str, allowed_content_types: set[str]) -> bool:
    # When intermediaries omit content-type, rely on extension and deep ingest validation.
    if not content_type:
        return True
    normalized = content_type.split(";", maxsplit=1)[0].strip().lower()
    return normalized in allowed_content_types


def validate_cbz_upload_policy(upload: FileUploadLike) -> str | None:
    filename = _upload_filename(upload)
    if not _extension_allowed(filename, ALLOWED_CBZ_EXTENSIONS):
        allowed = ", ".join(sorted(ALLOWED_CBZ_EXTENSIONS))
        return f"Unsupported file extension for CBZ upload. Allowed: {allowed}"

    content_type = _upload_content_type(upload)
    if not _content_type_allowed(content_type, ALLOWED_CBZ_CONTENT_TYPES):
        allowed = ", ".join(sorted(ALLOWED_CBZ_CONTENT_TYPES))
        return f"Unsupported content type for CBZ upload. Allowed: {allowed}"
    return None


def validate_page_upload_policy(upload: FileUploadLike) -> str | None:
    filename = _upload_filename(upload)
    if not _extension_allowed(filename, ALLOWED_PAGE_EXTENSIONS):
        allowed = ", ".join(sorted(ALLOWED_PAGE_EXTENSIONS))
        return f"Unsupported page image extension. Allowed: {allowed}"

    content_type = _upload_content_type(upload)
    if not _content_type_allowed(content_type, ALLOWED_PAGE_CONTENT_TYPES):
        allowed = ", ".join(sorted(ALLOWED_PAGE_CONTENT_TYPES))
        return f"Unsupported page image content type. Allowed: {allowed}"
    return None


def validate_saved_upload_size(path: Path, max_bytes: int, label: str) -> str | None:
    size_bytes = path.stat().st_size
    if size_bytes > max_bytes:
        return f"{label} exceeds the configured upload size limit ({size_bytes} bytes > {max_bytes} bytes)"
    return None


def upload_policy_error_info(message: str) -> tuple[str, int]:
    if "exceeds the configured upload size limit" in message:
        return "upload_too_large", 413
    if "Unsupported file extension" in message:
        return "unsupported_extension", 415
    if "Unsupported page image extension" in message:
        return "unsupported_extension", 415
    if "Unsupported content type" in message:
        return "unsupported_content_type", 415
    return "upload_policy_violation", 400


def request_is_secure(request: RequestLike) -> bool:
    scheme_obj = getattr(request, "scheme", "")
    scheme = str(scheme_obj).lower()
    if scheme == "https":
        return True

    forwarded_proto = _header_value(request, "X-Forwarded-Proto").split(",")[0].strip().lower()
    if forwarded_proto == "https":
        return True

    forwarded = _header_value(request, "Forwarded").lower()
    if "proto=https" in forwarded:
        return True

    environ_obj = getattr(request, "environ", None)
    if isinstance(environ_obj, dict):
        environ_map = cast(dict[object, object], environ_obj)
        url_scheme_obj = environ_map.get("wsgi.url_scheme", "")
        url_scheme = str(url_scheme_obj).lower()
        if url_scheme == "https":
            return True

    return False


def enforce_https_termination(request: RequestLike, response: ResponseLike | None = None) -> bool:
    if not REQUIRE_HTTPS:
        return True
    if request_is_secure(request):
        return True
    if response is not None:
        host = _header_value(request, "Host").strip()
        if host:
            response.status_code = 301
            response.content_type = "text/plain; charset=utf-8"
            response.headers["Location"] = f"https://{host}{request.path}"
            response.set_data("Redirecting to HTTPS")
    return False


def _ensure_csrf_token(request: RequestLike, response: ResponseLike) -> str:
    existing_token = request.cookies.get(CSRF_COOKIE_NAME, "")
    token = existing_token.strip()
    if token:
        return token

    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=False,
        samesite=SESSION_COOKIE_SAMESITE,
    )
    return token


def _inject_csrf_inputs(html: str, csrf_token: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        open_tag = match.group(0)
        return f'{open_tag}<input type="hidden" name="csrf_token" value="{escape(csrf_token)}" />'

    return _POST_FORM_OPEN_TAG_RE.sub(replacer, html)


def apply_security_markup(
    request: RequestLike,
    response: ResponseLike,
    html: str,
) -> str:
    if not CSRF_PROTECT:
        return html
    csrf_token = _ensure_csrf_token(request, response)
    return _inject_csrf_inputs(html, csrf_token)


def validate_csrf(request: RequestLike) -> bool:
    if not CSRF_PROTECT:
        return True

    form_token = request.form.get("csrf_token", "").strip()
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "").strip()
    if not form_token or not cookie_token:
        LOGGER.warning(
            "CSRF validation failed",
            event_type="security",
            client_ip=_request_client_ip(request),
            path=request.path,
        )
        return False
    valid = hmac.compare_digest(form_token, cookie_token)
    if not valid:
        LOGGER.warning(
            "CSRF token mismatch",
            event_type="security",
            client_ip=_request_client_ip(request),
            path=request.path,
        )
    return valid


def _admin_password_hash_digest(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_admin_password(password: str) -> bool:
    configured = ADMIN_PASSWORD_HASH.strip()
    if configured.startswith("sha256$"):
        expected = configured.split("$", maxsplit=1)[1]
        provided = _admin_password_hash_digest(password)
        return hmac.compare_digest(provided, expected)

    if configured.startswith("pbkdf2_sha256$"):
        parts = configured.split("$")
        if len(parts) != 4:
            return False
        _, rounds_raw, salt, expected = parts
        try:
            rounds = int(rounds_raw)
        except ValueError:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            rounds,
        ).hex()
        return hmac.compare_digest(derived, expected)

    return False


def _request_client_ip(request: RequestLike) -> str:
    forwarded_for = _header_value(request, "X-Forwarded-For")
    if forwarded_for:
        client = forwarded_for.split(",")[0].strip()
        if client:
            return client

    remote_addr_obj = getattr(request, "remote_addr", "")
    remote_addr = str(remote_addr_obj).strip()
    if remote_addr:
        return remote_addr
    return "unknown"


def _auth_key(request: RequestLike, username: str) -> str:
    client = _request_client_ip(request)
    normalized_user = username.strip().lower()
    return f"{client}:{normalized_user}"


def auth_lockout_seconds_remaining(request: RequestLike, username: str) -> int:
    key = _auth_key(request, username)
    now = time.time()
    with _AUTH_LOCK:
        locked_until = _AUTH_LOCKED_UNTIL.get(key, 0.0)
        if locked_until <= now:
            if key in _AUTH_LOCKED_UNTIL:
                _AUTH_LOCKED_UNTIL.pop(key)
            return 0
        return int(locked_until - now)


def record_auth_failure(request: RequestLike, username: str) -> int:
    key = _auth_key(request, username)
    client_ip = _request_client_ip(request)
    now = time.time()
    with _AUTH_LOCK:
        _prune_stale_auth_entries(now)
        attempts = _AUTH_FAILURE_TIMESTAMPS.get(key, [])
        window_floor = now - AUTH_WINDOW_SECONDS
        attempts = [attempt for attempt in attempts if attempt >= window_floor]
        attempts.append(now)
        _AUTH_FAILURE_TIMESTAMPS[key] = attempts

        if len(attempts) >= AUTH_MAX_FAILURES:
            _AUTH_LOCKED_UNTIL[key] = now + AUTH_LOCKOUT_SECONDS
            _AUTH_FAILURE_TIMESTAMPS[key] = []
            LOGGER.warning(
                "auth lockout triggered",
                event_type="security",
                username=username,
                client_ip=client_ip,
                lockout_seconds=AUTH_LOCKOUT_SECONDS,
            )
            return AUTH_LOCKOUT_SECONDS
        LOGGER.info(
            "auth failure recorded",
            event_type="security",
            username=username,
            client_ip=client_ip,
            attempt_count=len(attempts),
        )
        return 0


def _prune_stale_auth_entries(now: float) -> None:
    """Remove expired lockout entries to prevent unbounded memory growth.

    Must be called while holding ``_AUTH_LOCK``.
    """
    cutoff = now - AUTH_LOCKOUT_SECONDS * 2
    stale_keys = [key for key, locked_until in _AUTH_LOCKED_UNTIL.items() if locked_until < cutoff]
    for key in stale_keys:
        _AUTH_LOCKED_UNTIL.pop(key, None)
        _AUTH_FAILURE_TIMESTAMPS.pop(key, None)


def clear_auth_failures(request: RequestLike, username: str) -> None:
    key = _auth_key(request, username)
    with _AUTH_LOCK:
        if key in _AUTH_FAILURE_TIMESTAMPS:
            _AUTH_FAILURE_TIMESTAMPS.pop(key)
        if key in _AUTH_LOCKED_UNTIL:
            _AUTH_LOCKED_UNTIL.pop(key)


def _safe_next_url(value: str) -> str:
    candidate = value.strip()
    if not candidate.startswith("/"):
        return "/"
    if candidate.startswith("//"):
        return "/"
    return candidate


def encode_auth0_oauth_state(*, state: str, code_verifier: str, next_url: str) -> str:
    now = int(time.time())
    token = JWT_ENCODE(
        {"alg": "HS256", "typ": "JWT"},
        {
            "state": state,
            "code_verifier": code_verifier,
            "next_url": _safe_next_url(next_url),
            "iat": now,
            "exp": now + AUTH0_OAUTH_MAX_AGE,
        },
        SESSION_SECRET,
    )
    return token.decode("utf-8")


def decode_auth0_oauth_state(token: str) -> dict[str, str] | None:
    try:
        claims = JWT_DECODE(token, SESSION_SECRET)
        exp = claims.get("exp")
        if not isinstance(exp, int) or exp < int(time.time()):
            return None
        state = claims.get("state")
        code_verifier = claims.get("code_verifier")
        next_url = claims.get("next_url")
        if not isinstance(state, str) or not isinstance(code_verifier, str):
            return None
        resolved_next = next_url if isinstance(next_url, str) else "/"
        return {
            "state": state,
            "code_verifier": code_verifier,
            "next_url": _safe_next_url(resolved_next),
        }
    except (JoseError, ValueError):
        return None


def read_auth0_oauth_state(request: RequestLike) -> dict[str, str] | None:
    token = request.cookies.get(AUTH0_OAUTH_COOKIE_NAME, "").strip()
    if not token:
        return None
    return decode_auth0_oauth_state(token)


def set_auth0_oauth_cookie(
    response: ResponseLike,
    *,
    state: str,
    code_verifier: str,
    next_url: str,
) -> None:
    token = encode_auth0_oauth_state(state=state, code_verifier=code_verifier, next_url=next_url)
    response.set_cookie(
        AUTH0_OAUTH_COOKIE_NAME,
        token,
        max_age=AUTH0_OAUTH_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_auth0_oauth_cookie(response: ResponseLike) -> None:
    response.delete_cookie(AUTH0_OAUTH_COOKIE_NAME, path="/")


def begin_upload_session(username: str) -> tuple[bool, str, int]:
    normalized_username = username.strip().lower()
    if not normalized_username:
        return True, "", 0

    now = time.time()
    with _UPLOAD_LOCK:
        attempts = _UPLOAD_ATTEMPT_TIMESTAMPS.get(normalized_username, [])
        window_floor = now - UPLOAD_RATE_WINDOW_SECONDS
        attempts = [attempt for attempt in attempts if attempt >= window_floor]

        current_in_flight = _UPLOAD_IN_FLIGHT.get(normalized_username, 0)
        if current_in_flight >= UPLOAD_MAX_CONCURRENT_PER_USER:
            _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
            return False, "upload_concurrency_limited", 0

        if len(attempts) >= UPLOAD_RATE_MAX_REQUESTS:
            oldest_attempt = attempts[0]
            retry_after = int(max(1, oldest_attempt + UPLOAD_RATE_WINDOW_SECONDS - now))
            _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
            return False, "upload_rate_limited", retry_after

        attempts.append(now)
        _UPLOAD_ATTEMPT_TIMESTAMPS[normalized_username] = attempts
        _UPLOAD_IN_FLIGHT[normalized_username] = current_in_flight + 1
    return True, "", 0


def end_upload_session(username: str) -> None:
    normalized_username = username.strip().lower()
    if not normalized_username:
        return

    with _UPLOAD_LOCK:
        current_in_flight = _UPLOAD_IN_FLIGHT.get(normalized_username, 0)
        if current_in_flight <= 1:
            if normalized_username in _UPLOAD_IN_FLIGHT:
                _UPLOAD_IN_FLIGHT.pop(normalized_username)
            return
        _UPLOAD_IN_FLIGHT[normalized_username] = current_in_flight - 1


def begin_comic_ingest_session(
    *,
    wait_timeout_seconds: int | None = None,
    on_queued: Callable[[int], None] | None = None,
) -> tuple[bool, int, int]:
    if COMIC_INGEST_MAX_CONCURRENT <= 0:
        return True, 0, 0

    timeout_seconds = wait_timeout_seconds if wait_timeout_seconds is not None else COMIC_INGEST_QUEUE_WAIT_SECONDS
    timeout_seconds = timeout_seconds if timeout_seconds >= 0 else 0
    deadline = time.time() + timeout_seconds

    global _COMIC_INGEST_ACTIVE
    global _COMIC_INGEST_WAITING
    with _COMIC_INGEST_CONDITION:
        queued = False
        queue_position = 0
        while _COMIC_INGEST_ACTIVE >= COMIC_INGEST_MAX_CONCURRENT:
            if not queued:
                _COMIC_INGEST_WAITING += 1
                queued = True
                queue_position = _COMIC_INGEST_WAITING
            else:
                queue_position = _COMIC_INGEST_WAITING

            if on_queued is not None and queue_position > 0:
                try:
                    on_queued(queue_position)
                except Exception:
                    pass

            remaining = deadline - time.time()
            if remaining <= 0:
                if queued:
                    _COMIC_INGEST_WAITING -= 1
                timeout_retry_after = 1
                return False, timeout_retry_after, queue_position if queue_position else 1

            _COMIC_INGEST_CONDITION.wait(timeout=remaining)

        if queued:
            _COMIC_INGEST_WAITING -= 1
        _COMIC_INGEST_ACTIVE += 1
    return True, 0, queue_position


def end_comic_ingest_session() -> None:
    global _COMIC_INGEST_ACTIVE
    with _COMIC_INGEST_CONDITION:
        if _COMIC_INGEST_ACTIVE > 0:
            _COMIC_INGEST_ACTIVE -= 1
        _COMIC_INGEST_CONDITION.notify()


def check_post_rate_limit(request: RequestLike) -> int:
    """Return retry-after seconds if the client IP exceeds the POST rate limit, else 0."""
    client_ip = _request_client_ip(request)
    now = time.time()
    with _POST_RATE_LOCK:
        attempts = _POST_RATE_TIMESTAMPS.get(client_ip, [])
        window_floor = now - POST_RATE_WINDOW_SECONDS
        attempts = [ts for ts in attempts if ts >= window_floor]

        if len(attempts) >= POST_RATE_MAX_REQUESTS:
            oldest = attempts[0]
            retry_after = int(max(1, oldest + POST_RATE_WINDOW_SECONDS - now))
            _POST_RATE_TIMESTAMPS[client_ip] = attempts
            LOGGER.warning(
                "POST rate limit exceeded",
                event_type="security",
                client_ip=client_ip,
                retry_after=retry_after,
            )
            return retry_after

        attempts.append(now)
        _POST_RATE_TIMESTAMPS[client_ip] = attempts
    return 0


def validate_field_lengths(
    fields: dict[str, str],
    *,
    short: set[str] | None = None,
    long: set[str] | None = None,
    url: set[str] | None = None,
) -> str | None:
    """Return an error message if any field exceeds its length limit, else None."""
    for name, value in fields.items():
        if short and name in short:
            if len(value) > MAX_SHORT_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_SHORT_FIELD_LENGTH} chars)"
        elif url and name in url:
            if len(value) > MAX_URL_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_URL_FIELD_LENGTH} chars)"
        elif long and name in long:
            if len(value) > MAX_LONG_FIELD_LENGTH:
                return f"{name} exceeds maximum length ({MAX_LONG_FIELD_LENGTH} chars)"
    return None


def encode_session(username: str) -> str:
    now = int(time.time())
    token = JWT_ENCODE(
        {"alg": "HS256", "typ": "JWT"},
        {
            "sub": username,
            "iat": now,
            "exp": now + SESSION_MAX_AGE,
        },
        SESSION_SECRET,
    )
    return token.decode("utf-8")


def decode_session(token: str) -> str | None:
    try:
        claims = JWT_DECODE(token, SESSION_SECRET)

        exp = claims.get("exp")
        if not isinstance(exp, int):
            return None
        if exp < int(time.time()):
            return None

        username = claims.get("sub")
        if isinstance(username, str):
            return username
        return None
    except (JoseError, ValueError):
        return None


def current_user(request: RequestLike) -> str | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    return decode_session(token)


def set_login_cookie(response: ResponseLike, username: str) -> None:
    token = encode_session(username)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=SESSION_COOKIE_SAMESITE,
    )
    # Rotate CSRF token on login to prevent token-fixation attacks.
    new_csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        new_csrf,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        httponly=False,
        samesite=SESSION_COOKIE_SAMESITE,
    )


def clear_login_cookie(response: ResponseLike) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def user_menu_replacements(request: RequestLike) -> dict[str, str]:
    username = current_user(request)
    logged_in = username is not None
    display_name = ""
    if logged_in and username:
        try:
            local_user = get_local_user(username)
            display_name = local_user["display_name"] if local_user is not None else username
        except Exception:
            display_name = username
    role = current_user_role(request)
    is_admin = role in {"superadmin", "admin"}
    reports_current_attr = ' aria-current="page"' if request.path == "/admin/reports" else ""
    users_current_attr = ' aria-current="page"' if request.path == "/admin/users" else ""
    admin_reports_link = (
        f'<a href="/admin/reports"{reports_current_attr}>Reports</a>'
        f'<a href="/admin/users"{users_current_attr}>Users</a>'
        if is_admin
        else ""
    )
    login_hidden_attr = "hidden" if logged_in else ""
    profile_hidden_attr = "" if logged_in else "hidden"
    logout_hidden_attr = "" if logged_in else "hidden"
    user_menu_panel_content = (
        f'<p id="userMenuStatus" class="user-menu-status">'
        f"{'Logged in as ' + escape(display_name) + '.' if logged_in and username else 'Not logged in.'}"
        "</p>"
        f'<a id="userMenuLogin" class="user-menu-link" href="/account/login" {login_hidden_attr}>Login</a>'
        f'<a id="userMenuSignup" class="user-menu-link" href="https://fanic.media/account/auth0/signup" {login_hidden_attr}>Create an account</a>'
        f'<a id="userMenuProfile" class="user-menu-link" href="/user/profile" {profile_hidden_attr}>Profile</a>'
        "__USER_MENU_UPLOAD_LINK__"
        f'<a id="userMenuLogout" class="user-menu-link user-menu-logout" href="/account/logout" {logout_hidden_attr}>Logout</a>'
    )
    user_menu_html = (
        '<div class="user-menu">'
        '<button id="userMenuButton" class="user-menu-button" type="button" '
        'aria-haspopup="true" aria-expanded="false" aria-controls="userMenuPanel" '
        'title="User menu">'
        '<i class="fa-solid fa-user" aria-hidden="true"></i>'
        '<span class="sr-only">User menu</span>'
        "</button>"
        '<div id="userMenuPanel" class="user-menu-panel" hidden>'
        f"{user_menu_panel_content}"
        "</div>"
        "</div>"
    )
    return {
        "__USER_MENU_STATUS__": f"Logged in as {escape(display_name)}." if logged_in and username else "Not logged in.",
        "__USER_MENU_LOGIN_HIDDEN_ATTR__": login_hidden_attr,
        "__USER_MENU_PROFILE_HIDDEN_ATTR__": profile_hidden_attr,
        "__USER_MENU_LOGOUT_HIDDEN_ATTR__": logout_hidden_attr,
        "__USER_MENU_PANEL_CONTENT__": user_menu_panel_content,
        "__USER_MENU_HTML__": user_menu_html,
        "__SITE_TAGLINE__": "Fan Archive Nexus for Illustrated Comics",
        "__SITE_LOGO_HTML__": (
            '<h1 class="site-title">'
            '<a href="/" aria-label="FANIC home">'
            '<img class="site-logo" src="/static/logo.png" alt="FANIC Logo" />'
            "</a>"
            "</h1>"
        ),
        "__USER_MENU_UPLOAD_LINK__": "",
        "__ADMIN_REPORTS_LINK__": admin_reports_link,
    }


def _replace_markers(text: str, replacements: dict[str, str]) -> str:
    resolved = text
    for marker, value in replacements.items():
        resolved = resolved.replace(marker, value)
    return resolved


def _site_header_html(template_name: str, replacements: dict[str, str]) -> str:
    header_parts = site_header_parts_for_template(template_name)
    resolved_nav_links = _replace_markers(header_parts.nav_links, replacements)
    resolved_meta_html = _replace_markers(header_parts.meta_html, replacements)
    resolved_extra_html = _replace_markers(header_parts.extra_html, replacements)
    resolved_logo = _replace_markers(replacements.get("__SITE_LOGO_HTML__", ""), replacements)
    resolved_user_menu = _replace_markers(replacements.get("__USER_MENU_HTML__", ""), replacements)

    return (
        '<header class="site-header">'
        '<div class="site-header-row">'
        f"{resolved_logo}"
        f"{resolved_meta_html}"
        '<div class="header-actions">'
        '<nav class="site-nav" aria-label="Primary">'
        f"{resolved_nav_links}"
        "</nav>"
        f"{resolved_user_menu}"
        "</div>"
        f"{resolved_extra_html}"
        "</div>"
        "</header>"
    )


def _theme_value_is_safe(value: str) -> bool:
    if not value or len(value) > 120:
        return False
    if "{" in value or "}" in value or ";" in value or "<" in value or ">" in value:
        return False
    return bool(SAFE_THEME_VALUE_PATTERN.match(value))


def _normalize_theme_var_name(name: object) -> str:
    text = str(name).strip()
    while text.startswith("--"):
        text = text[2:]
    return text.replace("_", "-")


def _extract_theme_overrides(toml_text: str) -> dict[str, dict[str, str]]:
    parsed: dict[str, object] = tomllib.loads(toml_text)

    result: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    for theme_name in ("light", "dark"):
        section = parsed.get(theme_name, {})
        if not isinstance(section, dict):
            continue
        section_map = cast(dict[object, object], section)
        for raw_name, raw_value in section_map.items():
            var_name = _normalize_theme_var_name(raw_name)
            if var_name not in THEME_VAR_ALLOWLIST:
                continue
            if not isinstance(raw_value, str):
                continue
            value = raw_value.strip()
            if not _theme_value_is_safe(value):
                continue
            result[theme_name][var_name] = value
    return result


def _custom_theme_style_tag(request: RequestLike) -> str:
    username = current_user(request)
    preference = get_user_theme_preference(username)
    if not preference["enabled"]:
        return ""
    toml_text = preference["toml_text"].strip()
    if not toml_text:
        return ""

    try:
        overrides = _extract_theme_overrides(toml_text)
    except tomllib.TOMLDecodeError:
        return ""

    light_pairs = overrides["light"]
    dark_pairs = overrides["dark"]
    if not light_pairs and not dark_pairs:
        return ""

    css_chunks: list[str] = ['<style id="customThemeOverrides">\n']
    if light_pairs:
        css_chunks.append(":root {\n")
        for name, value in light_pairs.items():
            css_chunks.append(f"  --{name}: {value};\n")
        css_chunks.append("}\n")
    if dark_pairs:
        css_chunks.append(':root[data-theme="dark"] {\n')
        for name, value in dark_pairs.items():
            css_chunks.append(f"  --{name}: {value};\n")
        css_chunks.append("}\n")
    css_chunks.append("</style>")
    return "".join(css_chunks)


def rating_badge_html(rating: object) -> str:
    rating_text = str(rating if rating else "Not Rated").strip()
    safe_rating = rating_text if rating_text else "Not Rated"
    icon_name = RATING_ICON_BY_NAME.get(safe_rating)
    safe_label = escape(safe_rating)
    if not icon_name:
        return f'<span class="rating-badge"><span>{safe_label}</span></span>'

    safe_icon = escape(icon_name)
    return (
        '<span class="rating-badge">'
        f'<img class="rating-logo" src="/static/{safe_icon}" alt="" aria-hidden="true" />'
        f"<span>{safe_label}</span>"
        "</span>"
    )


def render_html_template(
    request: RequestLike,
    response: ResponseLike,
    template_name: str,
    replacements: dict[str, str] | None = None,
) -> ResponseLike:
    html = (STATIC_ROOT / template_name).read_text(encoding="utf-8")
    merged = user_menu_replacements(request)
    if replacements:
        merged.update(replacements)
    merged["__SITE_HEAD_ASSETS__"] = SITE_HEAD_ASSETS_HTML
    merged["__SITE_HEADER_HTML__"] = _site_header_html(template_name, merged)
    merged["__SITE_COMMON_SCRIPTS__"] = SITE_COMMON_SCRIPTS_HTML

    for marker, value in merged.items():
        html = html.replace(marker, value)

    custom_theme_style = _custom_theme_style_tag(request)
    if custom_theme_style and "</head>" in html:
        html = html.replace("</head>", f"{custom_theme_style}\n  </head>", 1)

    # Add the global footer to styled site pages without editing each template.
    if "/static/styles.css" in html and "</body>" in html:
        html = html.replace("</body>", f"{SITE_FOOTER_HTML}\n  </body>", 1)

    html = apply_security_markup(request, response, html)

    response.status_code = 200
    response.content_type = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.set_data(html)
    return response


def save_uploaded_ingest(
    cbz_upload: FileUploadLike,
    metadata_upload: FileUploadLike | None,
) -> dict[str, object]:
    cbz_policy_error = validate_cbz_upload_policy(cbz_upload)
    if cbz_policy_error:
        raise ValueError(cbz_policy_error)

    cbz_filename = cbz_upload.filename if cbz_upload.filename else "upload.cbz"
    cbz_name = Path(cbz_filename).name
    metadata_name = (
        Path(metadata_upload.filename if metadata_upload.filename else "metadata.json").name
        if metadata_upload is not None
        else "metadata.json"
    )

    with TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        cbz_path = temp_root / cbz_name
        cbz_upload.save(cbz_path)

        cbz_size_error = validate_saved_upload_size(
            cbz_path,
            MAX_CBZ_UPLOAD_BYTES,
            "CBZ upload",
        )
        if cbz_size_error:
            raise ValueError(cbz_size_error)

        metadata_path: Path | None = None
        if metadata_upload is not None and metadata_upload.filename:
            metadata_path = temp_root / metadata_name
            metadata_upload.save(metadata_path)

        return ingest_cbz(cbz_path, metadata_path)


def page_file_for(work_id: str, image_name: str) -> Path:
    return WORKS_DIR / work_id / "pages" / image_name


def thumb_file_for(work_id: str, thumb_name: str) -> Path:
    return WORKS_DIR / work_id / "thumbs" / thumb_name


def media_url(path: str) -> str:
    trimmed = path.strip()
    if not trimmed:
        return ""
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed
    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed}"
    media_base = _SETTINGS.media_base_url.strip()
    if not media_base:
        return trimmed
    return f"{media_base.rstrip('/')}{trimmed}"
