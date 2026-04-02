"""security common domain implementation."""

import hmac
from collections.abc import Callable
from pathlib import Path
from typing import cast

import structlog

from fanic.cylinder_sites.common.protocols import FileUploadLike
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.settings import FANART_DIR
from fanic.settings import STATIC_ASSETS_DIR
from fanic.settings import get_settings

ASSET_ROOT = STATIC_ASSETS_DIR.resolve()
_SETTINGS = get_settings()
CSRF_COOKIE_NAME = "fanic_csrf"
REQUIRE_HTTPS = _SETTINGS.require_https_effective
CSRF_PROTECT = _SETTINGS.csrf_protect_effective
MAX_CBZ_UPLOAD_BYTES = _SETTINGS.max_cbz_upload_bytes
MAX_PAGE_UPLOAD_BYTES = _SETTINGS.max_page_upload_bytes
ALLOWED_CBZ_EXTENSIONS = set(_SETTINGS.allowed_cbz_extensions)
ALLOWED_CBZ_CONTENT_TYPES = set(_SETTINGS.allowed_cbz_content_types)
ALLOWED_PAGE_EXTENSIONS = set(_SETTINGS.allowed_page_extensions)
ALLOWED_PAGE_CONTENT_TYPES = set(_SETTINGS.allowed_page_content_types)
LOGGER = structlog.get_logger("fanic.http")


def path_parts(request: RequestLike) -> list[str]:
    return [segment for segment in request.path.split("/") if segment]


def route_tail(request: RequestLike, prefix_parts: list[str]) -> list[str] | None:
    parts = path_parts(request)
    if len(parts) < len(prefix_parts):
        return None
    if parts[: len(prefix_parts)] != prefix_parts:
        return None
    return parts[len(prefix_parts) :]


def safe_static_path(rel_path: str) -> Path | None:
    normalized_rel_path = rel_path.strip().lstrip("/")

    # Fanart media is stored under FANART_DIR but exposed at /static/fanart/*.
    if normalized_rel_path.startswith("fanart/"):
        fanart_rel_path = normalized_rel_path[len("fanart/") :]
        candidate = (FANART_DIR / fanart_rel_path).resolve()
        try:
            _ = candidate.relative_to(FANART_DIR)
        except ValueError:
            return None
        return candidate

    candidate = (ASSET_ROOT / normalized_rel_path).resolve()
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

        forwarded_proto_obj = environ_map.get("HTTP_X_FORWARDED_PROTO", "")
        forwarded_proto = str(forwarded_proto_obj).split(",", maxsplit=1)[0].strip().lower()
        if forwarded_proto == "https":
            return True

        forwarded_ssl_obj = environ_map.get("HTTP_X_FORWARDED_SSL", "")
        forwarded_ssl = str(forwarded_ssl_obj).strip().lower()
        if forwarded_ssl in {"on", "1", "true"}:
            return True

        front_end_https_obj = environ_map.get("HTTP_FRONT_END_HTTPS", "")
        front_end_https = str(front_end_https_obj).strip().lower()
        if front_end_https in {"on", "1", "true"}:
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
