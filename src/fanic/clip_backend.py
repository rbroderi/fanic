import os
import time
from typing import cast

import open_clip
import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
import torch
from tqdm import tqdm

from fanic.settings import get_settings

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


def _call0(obj: object | None, name: str) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member()
    except Exception:
        return None


def _call1(obj: object | None, name: str, arg1: object) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member(arg1)
    except Exception:
        return None


def _call_kw(
    obj: object | None,
    name: str,
    *args: object,
    **kwargs: object,
) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member(*args, **kwargs)
    except Exception:
        return None


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

    progress = tqdm(
        total=3,
        desc="Loading CLIP backend",
        unit="step",
        leave=False,
        disable=not _VERBOSE_LOAD,
    )

    try:
        cuda_obj = getattr(torch_mod, "cuda", None)
        is_available = _call0(cuda_obj, "is_available")
        _device = "cuda" if bool(is_available) else "cpu"
        _ = progress.update(1)
        progress.set_postfix_str(f"device={_device}")

        created = _call_kw(
            open_clip_mod,
            "create_model_and_transforms",
            _MODEL_NAME,
            pretrained=_MODEL_PRETRAINED,
            force_quick_gelu=True,
            cache_dir=_CACHE_DIR,
        )
        if not isinstance(created, tuple):
            _last_load_failed_at = time.time()
            progress.close()
            return False

        created_tuple = cast(tuple[object, ...], created)
        if len(created_tuple) < 3:
            _last_load_failed_at = time.time()
            progress.close()
            return False

        model = created_tuple[0]
        preprocess = created_tuple[2]
        moved_model = _call1(model, "to", _device)
        if moved_model is None:
            _last_load_failed_at = time.time()
            progress.close()
            return False

        tokenizer = _call1(open_clip_mod, "get_tokenizer", _MODEL_NAME)
        if tokenizer is None:
            _last_load_failed_at = time.time()
            progress.close()
            return False

        _model = moved_model
        _ = _call0(_model, "eval")
        _preprocess = preprocess
        _tokenizer = tokenizer
        _torch_mod = torch_mod

        _ = progress.update(2)
        progress.set_postfix_str("ready")
        progress.close()
        _last_load_failed_at = 0.0
        return True
    except Exception:
        _model = None
        _preprocess = None
        _tokenizer = None
        _torch_mod = None
        _last_load_failed_at = time.time()
        progress.close()
        return False


def get_backend() -> tuple[object, object, object, object, str] | None:
    if not ensure_backend_loaded():
        return None
    if _model is None or _preprocess is None or _tokenizer is None or _torch_mod is None:
        return None
    return _model, _preprocess, _tokenizer, _torch_mod, _device
