import json
import logging
import socket
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from typing import TypedDict
from typing import cast
from typing import override
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from fanic.settings import get_settings


class ModerationResult(TypedDict):
    path: str
    allow: bool
    style: str
    style_debug: dict[str, object]
    style_confidences: dict[str, float]
    nsfw_score: float
    nsfw_confidences: dict[str, float]
    reasons: list[str]
    manual_review_required: bool
    manual_review_reason: str
    manual_review_confidence: float


_SETTINGS = get_settings()
_EXPLICIT_MIN_THRESHOLD = _SETTINGS.explicit_min_threshold
_EXPLICIT_MAX_THRESHOLD = _SETTINGS.explicit_max_threshold
_STYLE_MAX_CONFIDENCE_PHOTOREALISTIC = _SETTINGS.style_max_confidence_photorealistic
_ALLOWED_STYLES = {"comic", "illustrated", "painterly", "anime", "cgi"}
_LOGGER = logging.getLogger(__name__)
_nsfw_detector_cache: object | None = None
_style_classifier_cache: object | None = None


class _UnixHTTPConnection(HTTPConnection):
    _socket_path: str
    sock: socket.socket | None

    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__(host="localhost", timeout=timeout)
        self._socket_path = socket_path

    @override
    def connect(self) -> None:
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.settimeout(float(self.timeout) if self.timeout is not None else None)
        unix_socket.connect(self._socket_path)
        self.sock = unix_socket


def _get_nsfw_detector_module() -> object:
    global _nsfw_detector_cache
    detector = _nsfw_detector_cache
    if detector is not None:
        return detector
    import fanic.nsfw_detector as detector_module

    _nsfw_detector_cache = detector_module
    return detector_module


def _get_style_classifier_module() -> object:
    global _style_classifier_cache
    classifier = _style_classifier_cache
    if classifier is not None:
        return classifier
    import fanic.style_classifier as classifier_module

    _style_classifier_cache = classifier_module
    return classifier_module


def _sidecar_base_url() -> str:
    configured = getattr(_SETTINGS, "moderation_sidecar_url", "")
    value = str(configured).strip()
    if value.startswith("unix:"):
        return value
    return value.rstrip("/")


def _sidecar_uses_unix_socket() -> bool:
    return _sidecar_base_url().startswith("unix:")


def _sidecar_socket_path() -> str:
    if not _sidecar_uses_unix_socket():
        return ""
    return _sidecar_base_url()[len("unix:") :].strip()


def _sidecar_enabled() -> bool:
    return bool(_sidecar_base_url())


def _sidecar_timeout_seconds() -> float:
    raw_timeout = getattr(_SETTINGS, "moderation_sidecar_timeout_seconds", 20.0)
    timeout = float(raw_timeout)
    return timeout if timeout > 0 else 20.0


def _sidecar_headers(content_type: str) -> dict[str, str]:
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
    }
    raw_token = getattr(_SETTINGS, "moderation_sidecar_token", "")
    token = str(raw_token).strip()
    if token:
        headers["X-Fanic-Moderation-Token"] = token
    return headers


def _decode_sidecar_result(payload: object, *, fallback_path: str) -> ModerationResult:
    data: dict[str, object] = cast(dict[str, object], payload) if isinstance(payload, dict) else {}

    raw_path = data.get("path")
    path = str(raw_path).strip() if raw_path is not None else ""
    if not path:
        path = fallback_path

    raw_allow = data.get("allow")
    allow = bool(raw_allow)

    raw_style = data.get("style")
    style = str(raw_style).strip().lower() if raw_style is not None else "unknown"

    raw_style_debug = data.get("style_debug")
    style_debug: dict[str, object] = (
        cast(dict[str, object], raw_style_debug) if isinstance(raw_style_debug, dict) else {}
    )

    raw_style_conf = data.get("style_confidences")
    style_conf: dict[str, float] = {}
    if isinstance(raw_style_conf, dict):
        for key, value in cast(dict[str, object], raw_style_conf).items():
            if not isinstance(value, (str, int, float)):
                continue
            try:
                style_conf[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

    raw_nsfw = data.get("nsfw_score")
    if isinstance(raw_nsfw, (str, int, float)):
        try:
            nsfw_score = float(raw_nsfw)
        except (TypeError, ValueError):
            nsfw_score = 0.0
    else:
        nsfw_score = 0.0

    raw_nsfw_conf = data.get("nsfw_confidences")
    nsfw_conf: dict[str, float] = {}
    if isinstance(raw_nsfw_conf, dict):
        for key, value in cast(dict[str, object], raw_nsfw_conf).items():
            if not isinstance(value, (str, int, float)):
                continue
            try:
                nsfw_conf[str(key)] = float(value)
            except (TypeError, ValueError):
                continue

    raw_reasons = data.get("reasons")
    reasons = [str(item) for item in cast(list[object], raw_reasons)] if isinstance(raw_reasons, list) else []

    raw_review_required = data.get("manual_review_required")
    manual_review_required = bool(raw_review_required)
    raw_review_reason = data.get("manual_review_reason")
    manual_review_reason = str(raw_review_reason).strip() if raw_review_reason is not None else ""
    raw_review_confidence = data.get("manual_review_confidence")
    if isinstance(raw_review_confidence, (str, int, float)):
        try:
            manual_review_confidence = float(raw_review_confidence)
        except (TypeError, ValueError):
            manual_review_confidence = 0.0
    else:
        manual_review_confidence = 0.0

    return {
        "path": path,
        "allow": allow,
        "style": style,
        "style_debug": dict(style_debug),
        "style_confidences": style_conf,
        "nsfw_score": nsfw_score,
        "nsfw_confidences": nsfw_conf,
        "reasons": reasons,
        "manual_review_required": manual_review_required,
        "manual_review_reason": manual_review_reason,
        "manual_review_confidence": manual_review_confidence,
    }


def _sidecar_json_request(
    endpoint: str,
    *,
    method: str,
    body: bytes,
    headers: dict[str, str],
) -> object | None:
    if _sidecar_uses_unix_socket():
        socket_path = _sidecar_socket_path()
        if not socket_path:
            _LOGGER.warning("Moderation sidecar socket path is empty")
            return None

        connection = _UnixHTTPConnection(socket_path=socket_path, timeout=_sidecar_timeout_seconds())
        started_at = time.perf_counter()
        try:
            connection.request(method, endpoint, body=body, headers=headers)
            response = connection.getresponse()
            if response.status >= 400:
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                _LOGGER.warning(
                    "Moderation sidecar request failed (%s): status=%s elapsed_ms=%s",
                    endpoint,
                    response.status,
                    elapsed_ms,
                )
                return None
            payload = json.loads(response.read().decode("utf-8"))
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            _LOGGER.info(
                "Moderation sidecar request completed (%s): elapsed_ms=%s",
                endpoint,
                elapsed_ms,
            )
            return payload
        except (TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            _LOGGER.warning(
                "Moderation sidecar unix request failed (%s): %s elapsed_ms=%s",
                endpoint,
                exc,
                elapsed_ms,
            )
            return None
        finally:
            connection.close()

    url = f"{_sidecar_base_url()}{endpoint}"
    request = Request(url=url, data=body, method=method, headers=headers)
    started_at = time.perf_counter()
    try:
        with urlopen(request, timeout=_sidecar_timeout_seconds()) as response:
            payload = json.loads(response.read().decode("utf-8"))
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            _LOGGER.info(
                "Moderation sidecar request completed (%s): elapsed_ms=%s",
                endpoint,
                elapsed_ms,
            )
            return payload
    except (
        HTTPError,
        URLError,
        TimeoutError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _LOGGER.warning(
            "Moderation sidecar request failed (%s): %s elapsed_ms=%s",
            endpoint,
            exc,
            elapsed_ms,
        )
        return None


def _post_sidecar(endpoint: str, *, body: bytes, headers: dict[str, str]) -> ModerationResult | None:
    payload = _sidecar_json_request(endpoint, method="POST", body=body, headers=headers)
    if payload is None:
        return None
    return _decode_sidecar_result(payload, fallback_path="")


def get_moderation_sidecar_health() -> dict[str, object]:
    if not _sidecar_enabled():
        return {"moderation_sidecar": "down", "detail": "unconfigured"}

    health_payload = _sidecar_json_request(
        "/health",
        method="GET",
        body=b"",
        headers={"Accept": "application/json"},
    )
    if not isinstance(health_payload, dict):
        return {"moderation_sidecar": "down"}
    health_payload_map = cast(dict[str, object], health_payload)

    is_ok = bool(health_payload_map.get("ok"))
    return {"moderation_sidecar": "up" if is_ok else "down"}


def _moderate_image_via_sidecar(path: str) -> ModerationResult | None:
    payload = json.dumps({"path": path}, separators=(",", ":")).encode("utf-8")
    result = _post_sidecar(
        "/moderate-image",
        body=payload,
        headers=_sidecar_headers("application/json"),
    )
    if result is None:
        return None
    if not result["path"]:
        result["path"] = path
    return result


def _moderate_image_bytes_via_sidecar(image_bytes: bytes, suffix: str = ".png") -> ModerationResult | None:
    normalized_suffix = suffix.strip() if suffix else ".png"
    headers = _sidecar_headers("application/octet-stream")
    headers["X-Fanic-File-Suffix"] = normalized_suffix
    result = _post_sidecar(
        "/moderate-image-bytes",
        body=image_bytes,
        headers=headers,
    )
    if result is None:
        return None
    if not result["path"]:
        result["path"] = "<bytes>"
    return result


def _nsfw_score_with_confidences(path: str) -> tuple[float, dict[str, float]]:
    detector_module = _get_nsfw_detector_module()
    score_fn = cast(
        Callable[[str], tuple[float, dict[str, float]]],
        getattr(detector_module, "nsfw_score_with_confidences"),
    )
    return score_fn(path)


def _classify_style_with_confidences(path: str) -> tuple[str, dict[str, float]]:
    classifier_module = _get_style_classifier_module()
    classify_fn = cast(
        Callable[[str], tuple[str, dict[str, float]]],
        getattr(classifier_module, "classify_style_with_confidences"),
    )
    return classify_fn(path)


def _style_classifier_debug_state() -> dict[str, object]:
    classifier_module = _get_style_classifier_module()
    debug_fn = cast(
        Callable[[], dict[str, object]],
        getattr(classifier_module, "get_style_classifier_debug_state"),
    )
    return debug_fn()


def initialize_moderation_models(*, force: bool = False) -> dict[str, bool]:
    if not force:
        return {
            "requested": False,
            "nsfw_ready": False,
            "style_ready": False,
        }

    detector_module = _get_nsfw_detector_module()
    classifier_module = _get_style_classifier_module()

    init_nsfw = cast(Callable[[], bool], getattr(detector_module, "initialize_nsfw_model"))
    init_style = cast(Callable[[], bool], getattr(classifier_module, "initialize_style_model"))

    nsfw_ready = init_nsfw()
    style_ready = init_style()
    return {
        "requested": True,
        "nsfw_ready": nsfw_ready,
        "style_ready": style_ready,
    }


def get_explicit_threshold() -> float:
    return _EXPLICIT_MIN_THRESHOLD


def get_explicit_max_threshold() -> float:
    return _EXPLICIT_MAX_THRESHOLD


def get_style_max_confidence_photorealistic() -> float:
    return _STYLE_MAX_CONFIDENCE_PHOTOREALISTIC


def _score(path: str) -> tuple[float, dict[str, float]]:
    try:
        score_raw, conf_raw = _nsfw_score_with_confidences(path)
        return float(score_raw), dict(conf_raw)
    except (TypeError, ValueError):
        return 0.0, {"sfw": 0.0, "explicit": 0.0}


def moderate_image(path: str) -> ModerationResult:
    if not _sidecar_enabled():
        raise RuntimeError("Moderation sidecar URL is required")

    remote_result = _moderate_image_via_sidecar(path)
    if remote_result is not None:
        return remote_result
    raise RuntimeError("Moderation sidecar unavailable")


def moderate_image_local(path: str) -> ModerationResult:

    style_raw, style_confidences = _classify_style_with_confidences(path)
    style = str(style_raw).strip().lower()
    style_debug: dict[str, object] = {}
    reasons: list[str] = []

    # First gate is style. Photorealistic content is blocked immediately.
    if style == "photorealistic":
        photoreal_confidence = float(style_confidences.get("photorealistic", 0.0))
        if _SETTINGS.style_min_confidence_photorealistic <= photoreal_confidence < _STYLE_MAX_CONFIDENCE_PHOTOREALISTIC:
            reasons.append("photorealistic image flagged for manual admin review")
            return {
                "path": path,
                "allow": True,
                "style": style,
                "style_debug": style_debug,
                "style_confidences": style_confidences,
                "nsfw_score": 0.0,
                "nsfw_confidences": {"sfw": 0.0, "explicit": 0.0},
                "reasons": reasons,
                "manual_review_required": True,
                "manual_review_reason": "photorealistic",
                "manual_review_confidence": photoreal_confidence,
            }

        reasons.append("photorealistic image blocked by confidence threshold")
        return {
            "path": path,
            "allow": False,
            "style": style,
            "style_debug": style_debug,
            "style_confidences": style_confidences,
            "nsfw_score": 0.0,
            "nsfw_confidences": {"sfw": 0.0, "explicit": 0.0},
            "reasons": reasons,
            "manual_review_required": False,
            "manual_review_reason": "",
            "manual_review_confidence": 0.0,
        }

    if style == "unknown":
        style_debug = _style_classifier_debug_state()
        _LOGGER.warning(
            "Style classification unknown for %s. style_confidences=%s debug=%s",
            path,
            style_confidences,
            style_debug,
        )

    # Unknown or unsupported style labels are treated as not allowed.
    if style not in _ALLOWED_STYLES:
        reasons.append(f"unsupported style classification: {style}")
        return {
            "path": path,
            "allow": False,
            "style": style,
            "style_debug": style_debug,
            "style_confidences": style_confidences,
            "nsfw_score": 0.0,
            "nsfw_confidences": {"sfw": 0.0, "explicit": 0.0},
            "reasons": reasons,
            "manual_review_required": False,
            "manual_review_reason": "",
            "manual_review_confidence": 0.0,
        }

    # Only score NSFW after the image has passed style gating.
    nsfw, nsfw_confidences = _score(path)
    manual_review_required = _EXPLICIT_MIN_THRESHOLD <= nsfw < _EXPLICIT_MAX_THRESHOLD
    manual_review_reason = "explicit" if manual_review_required else ""
    manual_review_confidence = nsfw if manual_review_required else 0.0

    return {
        "path": path,
        "allow": True,
        "style": style,
        "style_debug": style_debug,
        "style_confidences": style_confidences,
        "nsfw_score": nsfw,
        "nsfw_confidences": nsfw_confidences,
        "reasons": reasons,
        "manual_review_required": manual_review_required,
        "manual_review_reason": manual_review_reason,
        "manual_review_confidence": manual_review_confidence,
    }


def moderate_image_bytes(image_bytes: bytes, suffix: str = ".png") -> ModerationResult:
    if not _sidecar_enabled():
        raise RuntimeError("Moderation sidecar URL is required")

    remote_result = _moderate_image_bytes_via_sidecar(image_bytes, suffix=suffix)
    if remote_result is not None:
        return remote_result
    raise RuntimeError("Moderation sidecar unavailable")


def moderate_image_bytes_local(image_bytes: bytes, suffix: str = ".png") -> ModerationResult:
    from tempfile import NamedTemporaryFile

    from fanic.media import delete_file

    temp_path = ""
    try:
        # On Windows, PIL cannot reopen a NamedTemporaryFile while its handle is active.
        with NamedTemporaryFile(
            suffix=suffix if suffix else ".png",
            delete=False,
        ) as handle:
            _ = handle.write(image_bytes)
            handle.flush()
            temp_path = handle.name

        return moderate_image_local(temp_path)
    finally:
        if temp_path:
            try:
                delete_file(Path(temp_path), missing_ok=True)
            except OSError:
                pass


def suggested_rating_for_nsfw(nsfw_score: float) -> str | None:
    if nsfw_score >= _EXPLICIT_MAX_THRESHOLD:
        return "Explicit"
    return None


def scan_upload_folder(folder: str = "uploads") -> list[ModerationResult]:
    results: list[ModerationResult] = []
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return results

    for file_path in root.iterdir():
        if file_path.suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".avif",
            ".gif",
        }:
            continue
        result = moderate_image(str(file_path))
        results.append(result)
    return results
