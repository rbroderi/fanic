"""logging_utils common domain implementation."""

import secrets
import time
from collections.abc import Callable
from collections.abc import Iterable
from typing import cast

import structlog
from authlib.jose import jwt
from authlib.jose.errors import JoseError

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.settings import get_settings

_SETTINGS = get_settings()
SESSION_COOKIE_NAME = "fanic_session"
SESSION_SECRET = _SETTINGS.session_secret
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
}

JWTDecode = Callable[[str | bytes, object], dict[str, object]]
JWT_DECODE = cast(JWTDecode, jwt.decode)
LOGGER = structlog.get_logger("fanic.http")


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


def _header_value(request: RequestLike, header_name: str) -> str:
    headers_obj = getattr(request, "headers", None)
    if headers_obj is None:
        return ""
    if not hasattr(headers_obj, "get"):
        return ""
    getter = cast(Callable[[str, str], object], headers_obj.get)
    value_obj = getter(header_name, "")
    return str(value_obj)


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
