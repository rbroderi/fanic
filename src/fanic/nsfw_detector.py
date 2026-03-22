from __future__ import annotations

# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportGeneralTypeIssues=false, reportArgumentType=false, reportAny=false
import os
from pathlib import Path

import open_clip
import torch
from tqdm import tqdm

try:
    # Ensure PIL AVIF codec is registered when available.
    import pillow_avif  # type: ignore[import-not-found]  # noqa: F401
except Exception:
    pillow_avif = None

_MODEL_NAME = "ViT-L-14"
_MODEL_PRETRAINED = "openai"
_NSFW_PROMPTS_BY_CLASS: dict[str, list[str]] = {
    "sfw": [
        "a safe-for-work comic or illustration",
        "a non-sexual drawing or artwork",
        "a fully clothed character illustration",
        "a wholesome non-explicit scene",
    ],
    "explicit": [
        "a pornographic, explicit nudity image",
        "a sexually explicit adult image",
        "uncensored genital nudity",
        "graphic sexual content",
    ],
}
_NSFW_CLASS_NAMES = list(_NSFW_PROMPTS_BY_CLASS.keys())
_CACHE_DIR = os.getenv("FANIC_OPENCLIP_CACHE_DIR", str(Path.home() / ".cache" / "clip"))
_DEFAULT_LOGIT_SCALE = float(os.getenv("FANIC_NSFW_LOGIT_SCALE", "100.0"))

_model: object | None = None
_preprocess: object | None = None
_tokenizer: object | None = None
_text_emb: object | None = None
_torch_mod: object | None = None
_device: str = "cpu"
_load_attempted = False
_VERBOSE_LOAD = os.getenv("FANIC_MODEL_LOAD_LOGS", "1") != "0"


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


def _as_prob_0_1(value: object) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, score))


def _empty_nsfw_confidences() -> dict[str, float]:
    return {name: 0.0 for name in _NSFW_CLASS_NAMES}


def _ensure_loaded() -> bool:
    global _model
    global _preprocess
    global _tokenizer
    global _text_emb
    global _torch_mod
    global _device
    global _load_attempted

    if _model is not None and _preprocess is not None and _text_emb is not None:
        return True
    if _load_attempted:
        return False
    _load_attempted = True

    open_clip_mod = open_clip
    torch_mod = torch
    os.makedirs(_CACHE_DIR, exist_ok=True)
    progress = tqdm(
        total=5,
        desc="Loading NSFW model",
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
        if not isinstance(created, tuple) or len(created) < 3:
            progress.close()
            return False
        _ = progress.update(1)
        progress.set_postfix_str("model created")

        model = created[0]
        preprocess = created[2]
        moved_model = _call1(model, "to", _device)
        if moved_model is None:
            return False

        _model = moved_model
        _ = _call0(_model, "eval")
        _preprocess = preprocess
        _tokenizer = _call1(open_clip_mod, "get_tokenizer", _MODEL_NAME)
        if _tokenizer is None:
            progress.close()
            return False
        _ = progress.update(1)
        progress.set_postfix_str("tokenizer ready")

        no_grad = _call0(torch_mod, "no_grad")
        if no_grad is None:
            progress.close()
            return False

        with no_grad:
            all_prompts: list[str] = []
            class_ranges: list[tuple[str, int, int]] = []
            cursor = 0
            for class_name in _NSFW_CLASS_NAMES:
                prompts = _NSFW_PROMPTS_BY_CLASS.get(class_name, [])
                if not prompts:
                    continue
                start = cursor
                all_prompts.extend(prompts)
                cursor += len(prompts)
                class_ranges.append((class_name, start, cursor))

            if not all_prompts:
                progress.close()
                return False

            tokenized = _call1(_tokenizer, "__call__", all_prompts)
            if tokenized is None:
                progress.close()
                return False

            text_tokens = _call1(tokenized, "to", _device)
            if text_tokens is None:
                progress.close()
                return False

            text_emb = _call1(_model, "encode_text", text_tokens)
            if text_emb is None:
                progress.close()
                return False

            text_norm = _call_kw(text_emb, "norm", dim=-1, keepdim=True)
            if text_norm is None:
                progress.close()
                return False

            text_emb_normed = _call1(text_emb, "__truediv__", text_norm)
            if text_emb_normed is None:
                progress.close()
                return False

            class_embeds: list[object] = []
            for class_name, start, end in class_ranges:
                _ = class_name
                prompt_slice = _call1(text_emb_normed, "__getitem__", slice(start, end))
                if prompt_slice is None:
                    progress.close()
                    return False

                class_mean = _call_kw(prompt_slice, "mean", dim=0)
                if class_mean is None:
                    progress.close()
                    return False

                class_norm = _call_kw(class_mean, "norm", dim=-1, keepdim=True)
                if class_norm is None:
                    progress.close()
                    return False

                class_mean_normed = _call1(class_mean, "__truediv__", class_norm)
                if class_mean_normed is None:
                    progress.close()
                    return False

                class_embeds.append(class_mean_normed)

            if not class_embeds:
                progress.close()
                return False

            stacked_class_embeds = _call_kw(torch_mod, "stack", class_embeds, dim=0)
            if stacked_class_embeds is None:
                progress.close()
                return False

            _text_emb = stacked_class_embeds
            _torch_mod = torch_mod
            _ = progress.update(1)
            progress.set_postfix_str("class prototypes ready")
    except Exception:
        _model = None
        _preprocess = None
        _tokenizer = None
        _text_emb = None
        _torch_mod = None
        progress.close()
        return False

    _ = progress.update(1)
    progress.set_postfix_str("ready")
    progress.close()

    return True


def _nsfw_score_internal(path: str) -> tuple[float, dict[str, float]]:
    """Return explicit probability and per-class confidences."""
    if not _ensure_loaded():
        return 0.0, _empty_nsfw_confidences()

    try:
        from PIL import Image

        image = Image.open(path).convert("RGB")
        preprocessed = _call1(_preprocess, "__call__", image)
        if preprocessed is None:
            return 0.0, _empty_nsfw_confidences()

        unsqueezed = _call1(preprocessed, "unsqueeze", 0)
        if unsqueezed is None:
            return 0.0, _empty_nsfw_confidences()

        image_tensor = _call1(unsqueezed, "to", _device)
        if image_tensor is None:
            return 0.0, _empty_nsfw_confidences()

        no_grad = _call0(_torch_mod, "no_grad")
        if no_grad is None:
            return 0.0, _empty_nsfw_confidences()

        with no_grad:
            image_emb = _call1(_model, "encode_image", image_tensor)
            if image_emb is None:
                return 0.0, _empty_nsfw_confidences()

            image_norm = _call_kw(image_emb, "norm", dim=-1, keepdim=True)
            if image_norm is None:
                return 0.0, _empty_nsfw_confidences()

            image_emb_normed = _call1(image_emb, "__truediv__", image_norm)
            if image_emb_normed is None:
                return 0.0, _empty_nsfw_confidences()

            text_emb_t = getattr(_text_emb, "T", None)
            if text_emb_t is None:
                return 0.0, _empty_nsfw_confidences()

            logits = _call1(image_emb_normed, "__matmul__", text_emb_t)
            if logits is None:
                return 0.0, _empty_nsfw_confidences()

            logit_scale_value = _DEFAULT_LOGIT_SCALE
            model_logit_scale = getattr(_model, "logit_scale", None)
            model_logit_scale_exp = _call0(model_logit_scale, "exp")
            model_logit_scale_item = _call0(model_logit_scale_exp, "item")
            try:
                extracted_scale = float(model_logit_scale_item)
            except Exception:
                extracted_scale = None
            if extracted_scale is not None and extracted_scale > 0:
                logit_scale_value = extracted_scale

            scaled_logits = _call1(logits, "__mul__", logit_scale_value)
            if scaled_logits is not None:
                logits = scaled_logits

            logits0 = _call1(logits, "__getitem__", 0)
            if logits0 is None:
                return 0.0, _empty_nsfw_confidences()

            softmaxed = _call_kw(logits0, "softmax", dim=0)
            if softmaxed is None:
                return 0.0, _empty_nsfw_confidences()

            confidences = _empty_nsfw_confidences()
            for i, class_name in enumerate(_NSFW_CLASS_NAMES):
                class_prob_obj = _call1(softmaxed, "__getitem__", i)
                if class_prob_obj is None:
                    continue
                item = _call0(class_prob_obj, "item")
                if item is None:
                    continue
                confidences[class_name] = _as_prob_0_1(item)

            explicit_prob = confidences.get("explicit", 0.0)
            return explicit_prob, confidences
    except Exception:
        return 0.0, _empty_nsfw_confidences()


def nsfw_score(path: str) -> float:
    """Return explicit probability in the range [0.0, 1.0]."""
    score, _ = _nsfw_score_internal(path)
    return score


def nsfw_score_with_confidences(path: str) -> tuple[float, dict[str, float]]:
    """Return explicit probability and confidence for each NSFW class."""
    return _nsfw_score_internal(path)


if os.getenv("FANIC_PRELOAD_MODELS", "1") != "0":
    _ = _ensure_loaded()
