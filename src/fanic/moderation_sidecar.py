import json
import logging
from collections.abc import Callable
from collections.abc import Iterable
from typing import Final
from typing import cast
from urllib.parse import parse_qs

from fanic.moderation import get_explicit_threshold
from fanic.moderation import initialize_moderation_models
from fanic.moderation import moderate_image
from fanic.moderation import moderate_image_bytes
from fanic.settings import get_settings

_LOGGER = logging.getLogger(__name__)
_SETTINGS = get_settings()
_TOKEN_HEADER_NAME: Final[str] = "HTTP_X_FANIC_MODERATION_TOKEN"
StartResponse = Callable[[str, list[tuple[str, str]]], object]


def _json_response(
    start_response: StartResponse,
    payload: dict[str, object],
    status_code: int,
) -> Iterable[bytes]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    status_text = "OK" if status_code < 400 else "Error"
    status = f"{status_code} {status_text}"
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
    ]
    start_response(status, headers)
    return [body]


def _read_body_bytes(environ: dict[str, object]) -> bytes:
    raw_length = str(environ.get("CONTENT_LENGTH", "0")).strip()
    try:
        length = int(raw_length)
    except ValueError:
        length = 0
    if length <= 0:
        return b""

    stream = environ.get("wsgi.input")
    if stream is None:
        return b""

    read_fn = getattr(stream, "read", None)
    if not callable(read_fn):
        return b""

    payload = read_fn(length)
    return payload if isinstance(payload, bytes) else b""


def _is_authorized(environ: dict[str, object]) -> bool:
    configured = str(_SETTINGS.moderation_sidecar_token).strip()
    if not configured:
        return True
    provided = str(environ.get(_TOKEN_HEADER_NAME, "")).strip()
    return provided == configured


def _suffix_from_request(environ: dict[str, object]) -> str:
    header_suffix = str(environ.get("HTTP_X_FANIC_FILE_SUFFIX", "")).strip()
    if header_suffix:
        return header_suffix

    query_string = str(environ.get("QUERY_STRING", "")).strip()
    query = parse_qs(query_string)
    suffix_values = query.get("suffix", [])
    first_value = suffix_values[0].strip() if suffix_values else ""
    return first_value if first_value else ".png"


def app(environ: dict[str, object], start_response: StartResponse) -> Iterable[bytes]:
    path = str(environ.get("PATH_INFO", "")).strip()
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()

    if path == "/health" and method == "GET":
        return _json_response(
            start_response,
            {
                "ok": True,
                "service": "fanic-moderation-sidecar",
                "explicit_threshold": get_explicit_threshold(),
            },
            200,
        )

    if not _is_authorized(environ):
        return _json_response(start_response, {"detail": "unauthorized"}, 401)

    if path == "/moderate-image" and method == "POST":
        try:
            payload_obj = json.loads(_read_body_bytes(environ).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_response(start_response, {"detail": "invalid JSON body"}, 400)

        payload = cast(dict[str, object], payload_obj) if isinstance(payload_obj, dict) else {}
        raw_path = payload.get("path")
        normalized_path = str(raw_path).strip() if raw_path is not None else ""
        if not normalized_path:
            return _json_response(start_response, {"detail": "path is required"}, 422)

        result = moderate_image(normalized_path)
        payload = cast(dict[str, object], cast(object, result))
        return _json_response(start_response, payload, 200)

    if path == "/moderate-image-bytes" and method == "POST":
        image_bytes = _read_body_bytes(environ)
        if not image_bytes:
            return _json_response(start_response, {"detail": "request body is empty"}, 422)

        suffix = _suffix_from_request(environ)
        result = moderate_image_bytes(image_bytes, suffix=suffix)
        payload = cast(dict[str, object], cast(object, result))
        return _json_response(start_response, payload, 200)

    return _json_response(start_response, {"detail": "not found"}, 404)


def create_app() -> object:
    readiness = initialize_moderation_models(force=True)
    _LOGGER.info("Moderation sidecar startup readiness: %s", readiness)
    return app
