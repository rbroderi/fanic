import logging
import sys
import time
from contextlib import AbstractContextManager
from typing import Any
from typing import cast

import pillow_avif  # type: ignore[import-not-found]  # noqa: F401

from fanic.clip_backend import get_backend
from fanic.settings import get_settings

_MODEL_NAME = "ViT-L-14"
_MODEL_PRETRAINED = "openai"
_STYLE_PROMPTS: dict[str, list[str]] = {
    "photorealistic": [
        "a photorealistic photo",
        "a real-world photograph",
        "a candid photo taken with a camera",
        "a natural lighting portrait photo",
    ],
    "illustrated": [
        "a western comic illustration",
        "a hand-drawn comic panel",
        "inked line art with flat comic colors",
        "a stylized 2D cartoon illustration",
    ],
    "painterly": [
        "a painterly digital illustration",
        "a digitally painted artwork",
        "a soft brushstroke illustration",
        "a colorful concept art painting",
    ],
    "anime": [
        "an anime style drawing",
        "a manga or anime character illustration",
        "cel-shaded anime artwork",
        "a Japanese anime frame",
    ],
    "cgi": [
        "a 3D CGI render",
        "a computer-generated 3D scene",
        "a 3D modeled character render",
        "a synthetic ray-traced render",
    ],
}
_STYLE_NAMES = list(_STYLE_PROMPTS.keys())
_SETTINGS = get_settings()
_CACHE_DIR = _SETTINGS.openclip_cache_dir
_DEFAULT_STYLE_MIN_CONFIDENCE = _SETTINGS.style_min_confidence_effective
_MIN_CONFIDENCE_BY_STYLE = {"photorealistic": _SETTINGS.style_min_confidence_photorealistic}
_LOW_CONFIDENCE_FALLBACK_STYLE = "comic"
_PHOTO_BLOCK_MIN_MARGIN = _SETTINGS.photo_block_min_margin
_STYLE_MIN_TOP_PROB = _SETTINGS.style_min_top_prob
_STYLE_MIN_TOP_MARGIN = _SETTINGS.style_min_top_margin
_DEFAULT_LOGIT_SCALE = _SETTINGS.style_logit_scale
_LOAD_RETRY_SECONDS = _SETTINGS.style_load_retry_seconds

_model: object | None = None
_preprocess: object | None = None
_tokenizer: object | None = None
_text_emb: object | None = None
_torch_mod: object | None = None
_device: str = "cpu"
_last_load_failed_at = 0.0
_last_load_error = ""
_last_classify_error = ""
_LOGGER = logging.getLogger(__name__)


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


def _call_kw(obj: object | None, name: str, *args: object, **kwargs: object) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member(*args, **kwargs)
    except Exception:
        return None


def _call0_context_manager(
    obj: object | None,
    name: str,
) -> AbstractContextManager[Any] | None:
    value = _call0(obj, name)
    if value is None:
        return None
    enter = getattr(value, "__enter__", None)
    exit_ = getattr(value, "__exit__", None)
    if not callable(enter) or not callable(exit_):
        return None
    return cast(AbstractContextManager[Any], value)


def _as_float_or_none(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_int_or_none(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _ensure_loaded() -> bool:
    global _model
    global _preprocess
    global _tokenizer
    global _text_emb
    global _torch_mod
    global _device
    global _last_load_failed_at
    global _last_load_error

    if _model is not None and _preprocess is not None and _text_emb is not None:
        return True

    now = time.time()
    if _last_load_failed_at > 0 and (now - _last_load_failed_at) < _LOAD_RETRY_SECONDS:
        return False

    _last_load_error = ""

    try:
        backend = get_backend()
        if backend is None:
            _last_load_error = "shared clip backend not available"
            _last_load_failed_at = time.time()
            return False
        model, preprocess, tokenizer, torch_mod, device = backend
        _model = model
        _preprocess = preprocess
        _torch_mod = torch_mod
        _device = device

        _tokenizer = tokenizer

        no_grad = _call0_context_manager(torch_mod, "no_grad")
        if no_grad is None:
            _LOGGER.warning("Style torch.no_grad() unavailable during model init")
            _last_load_error = "torch.no_grad unavailable"
            _last_load_failed_at = time.time()
            return False

        with no_grad:
            all_style_labels: list[str] = []
            style_ranges: list[tuple[str, int, int]] = []
            cursor = 0
            for style_name in _STYLE_NAMES:
                prompts = _STYLE_PROMPTS.get(style_name, [])
                if not prompts:
                    continue
                start = cursor
                all_style_labels.extend(prompts)
                cursor += len(prompts)
                style_ranges.append((style_name, start, cursor))

            if not all_style_labels:
                _last_load_failed_at = time.time()
                return False

            tokenized = _call1(_tokenizer, "__call__", all_style_labels)
            if tokenized is None:
                _last_load_failed_at = time.time()
                return False
            text_tokens = _call1(tokenized, "to", _device)
            if text_tokens is None:
                _last_load_failed_at = time.time()
                return False

            prompt_text_emb = _call1(_model, "encode_text", text_tokens)
            if prompt_text_emb is None:
                _last_load_failed_at = time.time()
                return False

            text_norm = _call_kw(prompt_text_emb, "norm", dim=-1, keepdim=True)
            if text_norm is None:
                _last_load_failed_at = time.time()
                return False

            prompt_text_emb_normed = _call1(prompt_text_emb, "__truediv__", text_norm)
            if prompt_text_emb_normed is None:
                _last_load_failed_at = time.time()
                return False

            class_embeds: list[object] = []
            for style_name, start, end in style_ranges:
                _ = style_name
                prompt_slice = _call1(prompt_text_emb_normed, "__getitem__", slice(start, end))
                if prompt_slice is None:
                    _last_load_failed_at = time.time()
                    return False

                class_mean = _call_kw(prompt_slice, "mean", dim=0)
                if class_mean is None:
                    _last_load_failed_at = time.time()
                    return False

                class_norm = _call_kw(class_mean, "norm", dim=-1, keepdim=True)
                if class_norm is None:
                    _last_load_failed_at = time.time()
                    return False

                class_mean_normed = _call1(class_mean, "__truediv__", class_norm)
                if class_mean_normed is None:
                    _last_load_failed_at = time.time()
                    return False

                class_embeds.append(class_mean_normed)

            if not class_embeds:
                _last_load_failed_at = time.time()
                return False

            stacked_class_embeds = _call_kw(torch_mod, "stack", class_embeds, dim=0)
            if stacked_class_embeds is None:
                _last_load_failed_at = time.time()
                return False

            _text_emb = stacked_class_embeds
            _torch_mod = torch_mod
    except Exception as exc:
        _LOGGER.exception("Style model initialization failed")
        _model = None
        _preprocess = None
        _tokenizer = None
        _text_emb = None
        _torch_mod = None
        _last_load_error = repr(exc)
        _last_load_failed_at = time.time()
        return False

    _last_load_failed_at = 0.0
    _last_load_error = ""

    return True


def _empty_confidences() -> dict[str, float]:
    return {name: 0.0 for name in _STYLE_NAMES}


def _classify_style_internal(path: str) -> tuple[str, dict[str, float]]:
    global _last_classify_error

    if not _ensure_loaded():
        return "unknown", _empty_confidences()

    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        preprocessed = _call1(_preprocess, "__call__", image)
        if preprocessed is None:
            return "unknown", _empty_confidences()

        unsqueezed = _call1(preprocessed, "unsqueeze", 0)
        if unsqueezed is None:
            return "unknown", _empty_confidences()

        image_tensor = _call1(unsqueezed, "to", _device)
        if image_tensor is None:
            return "unknown", _empty_confidences()

        no_grad = _call0_context_manager(_torch_mod, "no_grad")
        if no_grad is None:
            return "unknown", _empty_confidences()

        with no_grad:
            image_emb = _call1(_model, "encode_image", image_tensor)
            if image_emb is None:
                return "unknown", _empty_confidences()

            image_norm = _call_kw(image_emb, "norm", dim=-1, keepdim=True)
            if image_norm is None:
                return "unknown", _empty_confidences()

            image_emb_normed = _call1(image_emb, "__truediv__", image_norm)
            if image_emb_normed is None:
                return "unknown", _empty_confidences()

            text_emb_t = getattr(_text_emb, "T", None)
            if text_emb_t is None:
                return "unknown", _empty_confidences()
            text_emb_t_obj: object = text_emb_t

            logits = _call1(image_emb_normed, "__matmul__", text_emb_t_obj)
            if logits is None:
                return "unknown", _empty_confidences()

            # CLIP logits should be scaled before softmax; otherwise probabilities are too flat.
            logit_scale_value = _DEFAULT_LOGIT_SCALE
            model_logit_scale = getattr(_model, "logit_scale", None)
            model_logit_scale_exp = _call0(model_logit_scale, "exp")
            model_logit_scale_item = _call0(model_logit_scale_exp, "item")
            extracted_scale = _as_float_or_none(model_logit_scale_item)
            if extracted_scale is not None and extracted_scale > 0:
                logit_scale_value = extracted_scale

            scaled_logits = _call1(logits, "__mul__", logit_scale_value)
            if scaled_logits is not None:
                logits = scaled_logits

            logits0 = _call1(logits, "__getitem__", 0)
            if logits0 is None:
                return "unknown", _empty_confidences()

            probs = _call_kw(logits0, "softmax", dim=0)
            confidences = _empty_confidences()
            if probs is not None:
                for i, name in enumerate(_STYLE_NAMES):
                    p_t = _call1(probs, "__getitem__", i)
                    p = _as_float_or_none(_call0(p_t, "item"))
                    if p is not None:
                        confidences[name] = p

            argmaxed = _call1(_torch_mod, "argmax", logits0)
            if argmaxed is None:
                return "unknown", confidences

            idx = _as_int_or_none(_call0(argmaxed, "item"))
            if idx is None:
                return "unknown", confidences

            fallback_style: str | None = None
            if idx < 0 or idx >= len(_STYLE_NAMES):
                return "unknown", confidences

            predicted_style = _STYLE_NAMES[idx]
            top_prob: float | None = None
            if predicted_style in confidences:
                top_prob = confidences[predicted_style]

            # If scores are near-tied, classification is uncertain. Fallback to comic.
            sorted_probs = sorted(confidences.values(), reverse=True)
            if len(sorted_probs) >= 2:
                top_gap = float(sorted_probs[0] - sorted_probs[1])
                if sorted_probs[0] < _STYLE_MIN_TOP_PROB or top_gap < _STYLE_MIN_TOP_MARGIN:
                    return _LOW_CONFIDENCE_FALLBACK_STYLE, confidences

            if predicted_style == "photorealistic":
                # Keep photoreal only when it is top class and leads drawn styles by margin.
                if top_prob is not None:
                    drawn_probs = [
                        confidence for style_name, confidence in confidences.items() if style_name != "photorealistic"
                    ]

                    if drawn_probs:
                        best_drawn = max(drawn_probs)
                        if (top_prob - best_drawn) >= _PHOTO_BLOCK_MIN_MARGIN:
                            return predicted_style, confidences

                return _LOW_CONFIDENCE_FALLBACK_STYLE, confidences

            # Per-style confidence gates: low-confidence predictions map to fallback style.
            min_confidence: float = float(
                _MIN_CONFIDENCE_BY_STYLE.get(
                    predicted_style,
                    _DEFAULT_STYLE_MIN_CONFIDENCE,
                )
            )
            if min_confidence > 0 and top_prob is not None and top_prob < min_confidence:
                fallback_style = _LOW_CONFIDENCE_FALLBACK_STYLE

        if fallback_style is not None:
            return fallback_style, confidences
        return _STYLE_NAMES[idx], confidences
    except Exception as exc:
        _last_classify_error = repr(exc)
        _LOGGER.exception("Style classification failed for image path=%s", path)
        return "unknown", _empty_confidences()


def classify_style(path: str) -> str:
    style, _ = _classify_style_internal(path)
    return style


def classify_style_with_confidences(path: str) -> tuple[str, dict[str, float]]:
    return _classify_style_internal(path)


def get_style_classifier_debug_state() -> dict[str, object]:
    return {
        "python_executable": sys.executable,
        "model_name": _MODEL_NAME,
        "model_pretrained": _MODEL_PRETRAINED,
        "cache_dir": _CACHE_DIR,
        "device": _device,
        "model_loaded": bool(_model is not None and _preprocess is not None and _text_emb is not None),
        "pillow_avif_registered": pillow_avif is not None,
        "last_load_error": _last_load_error,
        "last_classify_error": _last_classify_error,
        "last_load_failed_at": _last_load_failed_at,
    }


def initialize_style_model() -> bool:
    return _ensure_loaded()


if _SETTINGS.preload_models:
    _ = initialize_style_model()
