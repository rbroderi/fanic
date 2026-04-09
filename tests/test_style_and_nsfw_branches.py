from contextlib import nullcontext
from pathlib import Path
from typing import Any
from typing import Self
from typing import cast

import pytest

import fanic._nsfw_detector as nsfw_detector
import fanic.style_classifier as style_classifier

_LEGACY_NSFW_REASON = "Legacy nsfw detector internals were decommissioned; use remote moderation tests"
_NSFW_ANY: Any = cast(Any, nsfw_detector)


def _reset_style_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(style_classifier, "_model", None)
    monkeypatch.setattr(style_classifier, "_preprocess", None)
    monkeypatch.setattr(style_classifier, "_tokenizer", None)
    monkeypatch.setattr(style_classifier, "_text_emb", None)
    monkeypatch.setattr(style_classifier, "_torch_mod", None)
    monkeypatch.setattr(style_classifier, "_device", "cpu")
    monkeypatch.setattr(style_classifier, "_last_load_failed_at", 0.0)
    monkeypatch.setattr(style_classifier, "_last_load_error", "")
    monkeypatch.setattr(style_classifier, "_last_classify_error", "")


def _reset_nsfw_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_NSFW_ANY, "_model", None)
    monkeypatch.setattr(_NSFW_ANY, "_preprocess", None)
    monkeypatch.setattr(_NSFW_ANY, "_text_emb", None)
    monkeypatch.setattr(_NSFW_ANY, "_torch_mod", None)
    monkeypatch.setattr(_NSFW_ANY, "_device", "cpu")
    monkeypatch.setattr(_NSFW_ANY, "_load_attempted", False)


class _NoGradFactory:
    def no_grad(self) -> Any:
        return nullcontext()


class _FakePreprocessed:
    def unsqueeze(self, dim: int) -> Self:
        _ = dim
        return self

    def to(self, device: str) -> Self:
        _ = device
        return self


class _FakePreprocess:
    def __init__(self, value: object | None) -> None:
        self._value: object | None = value

    def __call__(self, image: object) -> object | None:
        _ = image
        return self._value


class _FakeItem:
    def __init__(self, value: object) -> None:
        self._value: object = value

    def item(self) -> object:
        return self._value


class _FakeSoftmax:
    def __init__(self, values: list[object]) -> None:
        self._values: list[object] = values

    def __getitem__(self, index: int) -> _FakeItem:
        return _FakeItem(self._values[index])


class _FakeLogits0:
    def __init__(self, probs: list[object]) -> None:
        self._probs: list[object] = probs

    def softmax(self, dim: int) -> _FakeSoftmax:
        _ = dim
        return _FakeSoftmax(self._probs)


class _FakeLogits:
    def __init__(self, probs: list[object]) -> None:
        self._probs: list[object] = probs

    def __getitem__(self, index: int) -> _FakeLogits0 | None:
        if index != 0:
            return None
        return _FakeLogits0(self._probs)

    def __mul__(self, value: float) -> Self:
        _ = value
        return self


class _FakeImageEmbedding:
    def __init__(self, probs: list[object]) -> None:
        self._probs: list[object] = probs

    def norm(self, dim: int, keepdim: bool) -> int:
        _ = (dim, keepdim)
        return 1

    def __matmul__(self, other: object) -> _FakeLogits:
        _ = other
        return _FakeLogits(self._probs)

    def __truediv__(self, other: object) -> Self:
        _ = other
        return self


class _FakeModelLogitScale:
    def __init__(self, value: float) -> None:
        self._value: float = value

    def exp(self) -> _FakeItem:
        return _FakeItem(self._value)


class _FakeStyleModel:
    def __init__(self, probs: list[object]) -> None:
        self.logit_scale: _FakeModelLogitScale = _FakeModelLogitScale(10.0)
        self._probs: list[object] = probs

    def encode_image(self, image_tensor: object) -> _FakeImageEmbedding:
        _ = image_tensor
        return _FakeImageEmbedding(self._probs)


class _FakeTorchWithArgmax:
    @staticmethod
    def no_grad() -> Any:
        return nullcontext()

    @staticmethod
    def argmax(logits0: object) -> _FakeItem:
        _ = logits0
        return _FakeItem(4)


class _FakeTorchNoGradOnly:
    @staticmethod
    def no_grad() -> Any:
        return nullcontext()


class _FakeNsfwModelNoneEncode:
    logit_scale: _FakeModelLogitScale = _FakeModelLogitScale(5.0)

    @staticmethod
    def encode_image(img: object) -> None:
        _ = img
        return None


class _FakeNsfwModelClamped:
    logit_scale: _FakeModelLogitScale = _FakeModelLogitScale(3.0)

    @staticmethod
    def encode_image(img: object) -> _FakeImageEmbedding:
        _ = img
        return _FakeImageEmbedding(["-0.5", "1.8"])


def test_style_ensure_loaded_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_style_state(monkeypatch)
    monkeypatch.setattr(style_classifier, "get_backend", lambda: None)

    loaded = style_classifier.initialize_style_model()

    assert loaded is False
    debug_state = style_classifier.get_style_classifier_debug_state()
    assert "shared clip backend not available" in str(debug_state["last_load_error"])


def test_style_ensure_loaded_token_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_style_state(monkeypatch)

    backend = (object(), object(), object(), _NoGradFactory(), "cpu")
    monkeypatch.setattr(style_classifier, "get_backend", lambda: backend)

    loaded = style_classifier.initialize_style_model()

    assert loaded is False


def test_style_unknown_when_backend_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_style_state(monkeypatch)
    monkeypatch.setattr(style_classifier, "_ensure_loaded", lambda: False)

    style, confidences = style_classifier.classify_style_with_confidences("ignored.png")

    assert style == "unknown"
    assert set(confidences.keys()) == {
        "photorealistic",
        "illustrated",
        "painterly",
        "anime",
        "cgi",
    }


def test_style_low_confidence_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_style_state(monkeypatch)

    monkeypatch.setattr(style_classifier, "_ensure_loaded", lambda: True)
    monkeypatch.setattr(style_classifier, "_preprocess", _FakePreprocess(_FakePreprocessed()))
    monkeypatch.setattr(
        style_classifier,
        "_model",
        _FakeStyleModel([0.20, 0.19, 0.18, 0.17, 0.26]),
    )
    monkeypatch.setattr(
        style_classifier,
        "_torch_mod",
        _FakeTorchWithArgmax(),
    )
    monkeypatch.setattr(style_classifier, "_text_emb", type("_T", (), {"T": object()})())

    media_path = Path(__file__).resolve().parent / "media" / "safe.png"
    style, confidences = style_classifier.classify_style_with_confidences(str(media_path))

    assert style == "comic"
    assert isinstance(confidences["cgi"], float)


def test_style_debug_state_includes_error_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_style_state(monkeypatch)
    monkeypatch.setattr(style_classifier, "_last_load_error", "load error")
    monkeypatch.setattr(style_classifier, "_last_classify_error", "classify error")

    debug_state = style_classifier.get_style_classifier_debug_state()

    assert debug_state["last_load_error"] == "load error"
    assert debug_state["last_classify_error"] == "classify error"
    assert "model_loaded" in debug_state


@pytest.mark.skip(reason=_LEGACY_NSFW_REASON)
def test_nsfw_load_attempt_short_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_nsfw_state(monkeypatch)
    monkeypatch.setattr(_NSFW_ANY, "_load_attempted", True)

    loaded = _NSFW_ANY.initialize_nsfw_model()

    assert loaded is False


@pytest.mark.skip(reason=_LEGACY_NSFW_REASON)
def test_nsfw_image_encode_failure_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_nsfw_state(monkeypatch)

    monkeypatch.setattr(nsfw_detector, "_ensure_loaded", lambda: True)
    monkeypatch.setattr(_NSFW_ANY, "_preprocess", _FakePreprocess(_FakePreprocessed()))
    monkeypatch.setattr(
        _NSFW_ANY,
        "_model",
        _FakeNsfwModelNoneEncode(),
    )
    monkeypatch.setattr(
        _NSFW_ANY,
        "_torch_mod",
        _FakeTorchNoGradOnly(),
    )
    monkeypatch.setattr(_NSFW_ANY, "_text_emb", type("_T", (), {"T": object()})())

    media_path = Path(__file__).resolve().parent / "media" / "safe.png"
    score, confidences = _NSFW_ANY.nsfw_score_with_confidences(str(media_path))

    assert score == 0.0
    assert confidences["explicit"] == 0.0


@pytest.mark.skip(reason=_LEGACY_NSFW_REASON)
def test_nsfw_confidence_mapping_clamps_probs(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_nsfw_state(monkeypatch)

    monkeypatch.setattr(nsfw_detector, "_ensure_loaded", lambda: True)
    monkeypatch.setattr(_NSFW_ANY, "_preprocess", _FakePreprocess(_FakePreprocessed()))
    monkeypatch.setattr(
        _NSFW_ANY,
        "_model",
        _FakeNsfwModelClamped(),
    )
    monkeypatch.setattr(
        _NSFW_ANY,
        "_torch_mod",
        _FakeTorchNoGradOnly(),
    )
    monkeypatch.setattr(_NSFW_ANY, "_text_emb", type("_T", (), {"T": object()})())

    media_path = Path(__file__).resolve().parent / "media" / "safe.png"
    score, confidences = _NSFW_ANY.nsfw_score_with_confidences(str(media_path))

    assert 0.0 <= score <= 1.0
    assert confidences["sfw"] == 0.0
    assert confidences["explicit"] == 1.0


def test_style_reset_state_after_fork_clears_loaded_cache() -> None:
    style_classifier._model = object()  # pyright: ignore[reportPrivateUsage]
    style_classifier._preprocess = object()  # pyright: ignore[reportPrivateUsage]
    style_classifier._tokenizer = object()  # pyright: ignore[reportPrivateUsage]
    style_classifier._text_emb = object()  # pyright: ignore[reportPrivateUsage]
    style_classifier._torch_mod = object()  # pyright: ignore[reportPrivateUsage]
    style_classifier._device = "cuda"  # pyright: ignore[reportPrivateUsage]
    style_classifier._last_load_failed_at = 12.0  # pyright: ignore[reportPrivateUsage]
    style_classifier._last_load_error = "x"  # pyright: ignore[reportPrivateUsage]
    style_classifier._last_classify_error = "y"  # pyright: ignore[reportPrivateUsage]

    style_classifier._reset_style_state_after_fork()  # pyright: ignore[reportPrivateUsage]

    assert style_classifier._model is None  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._preprocess is None  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._tokenizer is None  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._text_emb is None  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._torch_mod is None  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._device == "cpu"  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._last_load_failed_at == 0.0  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._last_load_error == ""  # pyright: ignore[reportPrivateUsage]
    assert style_classifier._last_classify_error == ""  # pyright: ignore[reportPrivateUsage]


@pytest.mark.skip(reason=_LEGACY_NSFW_REASON)
def test_nsfw_reset_state_after_fork_clears_loaded_cache() -> None:
    _NSFW_ANY._model = object()
    _NSFW_ANY._preprocess = object()
    _NSFW_ANY._text_emb = object()
    _NSFW_ANY._torch_mod = object()
    _NSFW_ANY._device = "cuda"
    _NSFW_ANY._load_attempted = True

    _NSFW_ANY._reset_nsfw_state_after_fork()

    assert _NSFW_ANY._model is None
    assert _NSFW_ANY._preprocess is None
    assert _NSFW_ANY._text_emb is None
    assert _NSFW_ANY._torch_mod is None
    assert _NSFW_ANY._device == "cpu"
    assert _NSFW_ANY._load_attempted is False
