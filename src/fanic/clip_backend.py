import os
import time
from typing import Any
from typing import cast

import open_clip
import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
import torch
from alive_progress import alive_bar

from fanic.settings import get_settings
from fanic.torch_helpers import call0
from fanic.torch_helpers import call1
from fanic.torch_helpers import call_kw

_SETTINGS = get_settings()
_CACHE_DIR = _SETTINGS.openclip_cache_dir
_MODEL_NAME = "ViT-L-14"
_MODEL_PRETRAINED = "openai"
_LOAD_RETRY_SECONDS = _SETTINGS.style_load_retry_seconds
_VERBOSE_LOAD = _SETTINGS.model_load_logs

_model: object | None = None
_preprocess: object | None = None
_tokenizer: object | None = None
_torch_mod: object | None = None
_device: str = "cpu"
_last_load_failed_at = 0.0


class _NoopProgress:
    def update(self, _step: int) -> None:
        return

    def set_postfix_str(self, _value: str) -> None:
        return

    def close(self) -> None:
        return


class _AliveProgress:
    _ctx: Any
    _bar: Any

    def __init__(self, total: int, title: str, unit: str) -> None:
        self._ctx = alive_bar(total=total, title=title, unit=unit)
        self._bar = self._ctx.__enter__()

    def update(self, step: int) -> None:
        for _ in range(max(0, int(step))):
            self._bar()

    def set_postfix_str(self, _value: str) -> None:
        return

    def close(self) -> None:
        self._ctx.__exit__(None, None, None)


def _build_progress() -> object:
    if not _VERBOSE_LOAD:
        return _NoopProgress()
    return _AliveProgress(
        total=3,
        title="Loading CLIP backend",
        unit="step",
    )


def ensure_backend_loaded() -> bool:
    global _model
    global _preprocess
    global _tokenizer
    global _torch_mod
    global _device
    global _last_load_failed_at

    if _model is not None and _preprocess is not None and _tokenizer is not None:
        return True

    now = time.time()
    if _last_load_failed_at > 0 and (now - _last_load_failed_at) < _LOAD_RETRY_SECONDS:
        return False

    open_clip_mod = open_clip
    torch_mod = torch
    os.makedirs(_CACHE_DIR, exist_ok=True)

    progress = _build_progress()

    try:
        cuda_obj = getattr(torch_mod, "cuda", None)
        is_available = call0(cuda_obj, "is_available")
        _device = "cuda" if bool(is_available) else "cpu"
        _ = call1(progress, "update", 1)
        _ = call1(progress, "set_postfix_str", f"device={_device}")

        created = call_kw(
            open_clip_mod,
            "create_model_and_transforms",
            _MODEL_NAME,
            pretrained=_MODEL_PRETRAINED,
            force_quick_gelu=True,
            cache_dir=_CACHE_DIR,
        )
        if not isinstance(created, tuple):
            _last_load_failed_at = time.time()
            _ = call0(progress, "close")
            return False

        created_tuple = cast(tuple[object, ...], created)
        if len(created_tuple) < 3:
            _last_load_failed_at = time.time()
            _ = call0(progress, "close")
            return False

        model = created_tuple[0]
        preprocess = created_tuple[2]
        moved_model = call1(model, "to", _device)
        if moved_model is None:
            _last_load_failed_at = time.time()
            _ = call0(progress, "close")
            return False

        tokenizer = call1(open_clip_mod, "get_tokenizer", _MODEL_NAME)
        if tokenizer is None:
            _last_load_failed_at = time.time()
            _ = call0(progress, "close")
            return False

        _model = moved_model
        _ = call0(_model, "eval")
        _preprocess = preprocess
        _tokenizer = tokenizer
        _torch_mod = torch_mod

        _ = call1(progress, "update", 2)
        _ = call1(progress, "set_postfix_str", "ready")
        _ = call0(progress, "close")
        _last_load_failed_at = 0.0
        return True
    except Exception:
        _model = None
        _preprocess = None
        _tokenizer = None
        _torch_mod = None
        _last_load_failed_at = time.time()
        _ = call0(progress, "close")
        return False


def get_backend() -> tuple[object, object, object, object, str] | None:
    if not ensure_backend_loaded():
        return None
    if _model is None or _preprocess is None or _tokenizer is None or _torch_mod is None:
        return None
    return _model, _preprocess, _tokenizer, _torch_mod, _device
