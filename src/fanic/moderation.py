import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from collections.abc import Callable
from typing import TypedDict
from typing import cast

from lazi.core import lazi

from fanic.settings import get_settings

with lazi:
    import fanic.nsfw_detector as _NSFW_DETECTOR
    import fanic.style_classifier as _STYLE_CLASSIFIER


class ModerationResult(TypedDict):
    path: str
    allow: bool
    style: str
    style_debug: dict[str, object]
    style_confidences: dict[str, float]
    nsfw_score: float
    nsfw_confidences: dict[str, float]
    reasons: list[str]


_SETTINGS = get_settings()
_EXPLICIT_THRESHOLD = _SETTINGS.explicit_threshold
_ALLOWED_STYLES = {"comic", "illustrated", "painterly", "anime", "cgi"}
_LOGGER = logging.getLogger(__name__)


def _nsfw_score_with_confidences(path: str) -> tuple[float, dict[str, float]]:
    score_fn = cast(
        Callable[[str], tuple[float, dict[str, float]]],
        getattr(_NSFW_DETECTOR, "nsfw_score_with_confidences"),
    )
    return score_fn(path)


def _classify_style_with_confidences(path: str) -> tuple[str, dict[str, float]]:
    classify_fn = cast(
        Callable[[str], tuple[str, dict[str, float]]],
        getattr(_STYLE_CLASSIFIER, "classify_style_with_confidences"),
    )
    return classify_fn(path)


def _style_classifier_debug_state() -> dict[str, object]:
    debug_fn = cast(
        Callable[[], dict[str, object]],
        getattr(_STYLE_CLASSIFIER, "get_style_classifier_debug_state"),
    )
    return debug_fn()


def initialize_moderation_models(*, force: bool = False) -> dict[str, bool]:
    should_initialize = force if force else _SETTINGS.preload_models
    if not should_initialize:
        return {
            "requested": False,
            "nsfw_ready": False,
            "style_ready": False,
        }

    init_nsfw = cast(Callable[[], bool], getattr(_NSFW_DETECTOR, "initialize_nsfw_model"))
    init_style = cast(Callable[[], bool], getattr(_STYLE_CLASSIFIER, "initialize_style_model"))

    nsfw_ready = init_nsfw()
    style_ready = init_style()
    return {
        "requested": True,
        "nsfw_ready": nsfw_ready,
        "style_ready": style_ready,
    }


def get_explicit_threshold() -> float:
    return _EXPLICIT_THRESHOLD


def _score(path: str) -> tuple[float, dict[str, float]]:
    try:
        score_raw, conf_raw = _nsfw_score_with_confidences(path)
        return float(score_raw), dict(conf_raw)
    except (TypeError, ValueError):
        return 0.0, {"sfw": 0.0, "explicit": 0.0}


def moderate_image(path: str) -> ModerationResult:
    style_raw, style_confidences = _classify_style_with_confidences(path)
    style = str(style_raw).strip().lower()
    style_debug: dict[str, object] = {}
    reasons: list[str] = []

    # First gate is style. Photorealistic content is blocked immediately.
    if style == "photorealistic":
        reasons.append("photorealistic image (only illustrated/comic content allowed)")
        return {
            "path": path,
            "allow": False,
            "style": style,
            "style_debug": style_debug,
            "style_confidences": style_confidences,
            "nsfw_score": 0.0,
            "nsfw_confidences": {"sfw": 0.0, "explicit": 0.0},
            "reasons": reasons,
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
        }

    # Only score NSFW after the image has passed style gating.
    nsfw, nsfw_confidences = _score(path)

    return {
        "path": path,
        "allow": True,
        "style": style,
        "style_debug": style_debug,
        "style_confidences": style_confidences,
        "nsfw_score": nsfw,
        "nsfw_confidences": nsfw_confidences,
        "reasons": reasons,
    }


def moderate_image_bytes(image_bytes: bytes, suffix: str = ".png") -> ModerationResult:
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

        return moderate_image(temp_path)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


def suggested_rating_for_nsfw(nsfw_score: float) -> str | None:
    if nsfw_score >= _EXPLICIT_THRESHOLD:
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
