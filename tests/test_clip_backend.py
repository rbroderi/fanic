from __future__ import annotations

from types import SimpleNamespace

import pytest

import fanic.clip_backend as clip_backend


class _DummyProgress:
    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = (args, kwargs)

    def update(self, value: int) -> None:
        _ = value

    def set_postfix_str(self, value: str) -> None:
        _ = value

    def close(self) -> None:
        return None


class _FakeModel:
    def __init__(self) -> None:
        self.eval_calls: int = 0

    def to(self, device: str) -> _FakeModel:
        _ = device
        return self

    def eval(self) -> _FakeModel:
        self.eval_calls += 1
        return self


def _reset_backend_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clip_backend, "_model", None)
    monkeypatch.setattr(clip_backend, "_preprocess", None)
    monkeypatch.setattr(clip_backend, "_tokenizer", None)
    monkeypatch.setattr(clip_backend, "_torch_mod", None)
    monkeypatch.setattr(clip_backend, "_device", "cpu")
    monkeypatch.setattr(clip_backend, "_last_load_failed_at", 0.0)
    monkeypatch.setattr(clip_backend, "_LOAD_RETRY_SECONDS", 5.0)
    monkeypatch.setattr(clip_backend, "_CACHE_DIR", ".")
    monkeypatch.setattr(clip_backend, "tqdm", _DummyProgress)


def test_ensure_backend_loaded_success_and_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_backend_state(monkeypatch)

    create_calls = {"count": 0}
    fake_model = _FakeModel()

    def create_model_and_transforms(
        *args: object, **kwargs: object
    ) -> tuple[object, object, object]:
        _ = (args, kwargs)
        create_calls["count"] += 1
        return fake_model, object(), "preprocess"

    def get_tokenizer(model_name: str) -> str:
        return f"tok:{model_name}"

    fake_open_clip = SimpleNamespace(
        create_model_and_transforms=create_model_and_transforms,
        get_tokenizer=get_tokenizer,
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))

    monkeypatch.setattr(clip_backend, "open_clip", fake_open_clip)
    monkeypatch.setattr(clip_backend, "torch", fake_torch)

    first = clip_backend.ensure_backend_loaded()
    second = clip_backend.ensure_backend_loaded()

    assert first is True
    assert second is True
    assert create_calls["count"] == 1

    backend = clip_backend.get_backend()
    assert backend is not None
    model, preprocess, tokenizer, torch_mod, device = backend
    assert model is fake_model
    assert preprocess == "preprocess"
    assert tokenizer == "tok:ViT-L-14"
    assert torch_mod is fake_torch
    assert device == "cpu"


def test_ensure_backend_loaded_retries_after_failure_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_backend_state(monkeypatch)

    create_calls = {"count": 0}

    def create_model_and_transforms(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        create_calls["count"] += 1
        return None

    def get_tokenizer(model_name: str) -> str:
        return f"tok:{model_name}"

    fake_open_clip = SimpleNamespace(
        create_model_and_transforms=create_model_and_transforms,
        get_tokenizer=get_tokenizer,
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))

    clock = {"value": 100.0}

    def fake_time() -> float:
        return float(clock["value"])

    monkeypatch.setattr(clip_backend, "open_clip", fake_open_clip)
    monkeypatch.setattr(clip_backend, "torch", fake_torch)
    monkeypatch.setattr("fanic.clip_backend.time.time", fake_time)

    first = clip_backend.ensure_backend_loaded()
    second = clip_backend.ensure_backend_loaded()

    assert first is False
    assert second is False
    assert create_calls["count"] == 1

    clock["value"] = 106.0
    third = clip_backend.ensure_backend_loaded()
    assert third is False
    assert create_calls["count"] == 2


def test_get_backend_returns_none_when_loader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_backend_state(monkeypatch)

    monkeypatch.setattr(clip_backend, "ensure_backend_loaded", lambda: False)
    assert clip_backend.get_backend() is None


def test_ensure_backend_loaded_handles_exception_and_resets_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_backend_state(monkeypatch)

    def create_model_and_transforms(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise RuntimeError("boom")

    def get_tokenizer(model_name: str) -> str:
        return f"tok:{model_name}"

    fake_open_clip = SimpleNamespace(
        create_model_and_transforms=create_model_and_transforms,
        get_tokenizer=get_tokenizer,
    )
    fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))

    monkeypatch.setattr(clip_backend, "open_clip", fake_open_clip)
    monkeypatch.setattr(clip_backend, "torch", fake_torch)

    loaded = clip_backend.ensure_backend_loaded()

    assert loaded is False
    assert clip_backend.get_backend() is None
