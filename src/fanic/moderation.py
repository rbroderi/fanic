from __future__ import annotations

import importlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, TypedDict, cast

StyleClassifier = Callable[[str], str]
NSFWScorer = Callable[[str], float]


class ModerationResult(TypedDict):
    path: str
    allow: bool
    style: str
    nsfw_score: float
    reasons: list[str]


_EXPLICIT_THRESHOLD = float(os.getenv("FANIC_EXPLICIT_THRESHOLD", "0.45"))


def _load_callable(
    module_name: str, callable_name: str
) -> Callable[[str], object] | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None

    member = getattr(module, callable_name, None)
    if callable(member):
        return cast(Callable[[str], object], member)
    return None


_classify_style_raw = _load_callable("style_classifier", "classify_style")
_nsfw_score_raw = _load_callable("nsfw_detector", "nsfw_score")


def _classify(path: str) -> str:
    if _classify_style_raw is None:
        return "unknown"
    return str(_classify_style_raw(path)).strip().lower()


def _score(path: str) -> float:
    if _nsfw_score_raw is None:
        return 0.0
    try:
        raw_score = _nsfw_score_raw(path)
        if isinstance(raw_score, (int, float, str)):
            return float(raw_score)
        return 0.0
    except (TypeError, ValueError):
        return 0.0


def moderate_image(path: str) -> ModerationResult:
    style = _classify(path)
    nsfw = _score(path)

    reasons: list[str] = []
    allow = True

    if style == "photorealistic":
        allow = False
        reasons.append("photorealistic image (only illustrated/comic content allowed)")

    return {
        "path": path,
        "allow": allow,
        "style": style,
        "nsfw_score": nsfw,
        "reasons": reasons,
    }


def moderate_image_bytes(image_bytes: bytes, suffix: str = ".png") -> ModerationResult:
    with NamedTemporaryFile(suffix=suffix or ".png") as handle:
        _ = handle.write(image_bytes)
        handle.flush()
        return moderate_image(handle.name)


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
