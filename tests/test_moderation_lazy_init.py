# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
from types import SimpleNamespace
from typing import Any

import pytest

import fanic.moderation as moderation


def test_initialize_moderation_models_skips_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(moderation, "_SETTINGS", SimpleNamespace(preload_models=False))

    result = moderation.initialize_moderation_models()

    assert result == {
        "requested": False,
        "nsfw_ready": False,
        "style_ready": False,
    }


def test_initialize_moderation_models_forces_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(moderation, "_SETTINGS", SimpleNamespace(preload_models=False))

    init_calls: list[str] = []

    class FakeModule:
        def initialize_nsfw_model(self) -> bool:
            init_calls.append("nsfw")
            return True

        def initialize_style_model(self) -> bool:
            init_calls.append("style")
            return True

    fake = FakeModule()
    monkeypatch.setattr(moderation, "_get_nsfw_detector_module", lambda: fake)
    monkeypatch.setattr(moderation, "_get_style_classifier_module", lambda: fake)

    result = moderation.initialize_moderation_models(force=True)

    assert result == {
        "requested": True,
        "nsfw_ready": True,
        "style_ready": True,
    }
    assert init_calls == ["nsfw", "style"]


def test_initialize_moderation_models_skips_when_sidecar_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        moderation,
        "_SETTINGS",
        SimpleNamespace(
            preload_models=True,
            moderation_sidecar_url="http://127.0.0.1:8091",
        ),
    )

    result = moderation.initialize_moderation_models()

    assert result == {
        "requested": False,
        "nsfw_ready": False,
        "style_ready": False,
    }


def test_moderate_image_bytes_raises_when_sidecar_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        moderation,
        "_SETTINGS",
        SimpleNamespace(
            moderation_sidecar_url="",
            moderation_sidecar_timeout_seconds=5.0,
            moderation_sidecar_token="",
        ),
    )

    with pytest.raises(RuntimeError, match="Moderation sidecar URL is required"):
        _ = moderation.moderate_image_bytes(b"abc", suffix=".jpg")


def test_moderate_image_bytes_uses_sidecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        moderation,
        "_SETTINGS",
        SimpleNamespace(
            moderation_sidecar_url="http://127.0.0.1:8091",
            moderation_sidecar_timeout_seconds=5.0,
            moderation_sidecar_token="",
        ),
    )

    class _FakeResponse:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            _ = (exc_type, exc, tb)
            return None

        def read(self) -> bytes:
            return (
                b'{"path":"<bytes>","allow":true,"style":"comic","style_debug":{},'
                b'"style_confidences":{"comic":1.0},"nsfw_score":0.1,'
                b'"nsfw_confidences":{"sfw":0.9,"explicit":0.1},"reasons":[]}'
            )

    def _fake_urlopen(request: object, timeout: float) -> Any:
        _ = timeout
        request_obj = request
        full_url = getattr(request_obj, "full_url", "")
        assert full_url == "http://127.0.0.1:8091/moderate-image-bytes"
        return _FakeResponse()

    monkeypatch.setattr(moderation, "urlopen", _fake_urlopen)

    result = moderation.moderate_image_bytes(b"abc", suffix=".jpg")

    assert result["allow"] is True
    assert result["style"] == "comic"
    assert result["nsfw_score"] == 0.1


def test_moderate_image_bytes_raises_when_sidecar_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        moderation,
        "_SETTINGS",
        SimpleNamespace(
            moderation_sidecar_url="http://127.0.0.1:8091",
            moderation_sidecar_timeout_seconds=0.01,
            moderation_sidecar_token="",
        ),
    )

    def _fake_urlopen(*args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise TimeoutError("timed out")

    monkeypatch.setattr(moderation, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match="Moderation sidecar unavailable"):
        _ = moderation.moderate_image_bytes(b"abc", suffix=".jpg")


def test_get_moderation_sidecar_health_uses_unix_socket_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        moderation,
        "_SETTINGS",
        SimpleNamespace(
            moderation_sidecar_url="unix:/run/fanic/fanic-moderation.sock",
            moderation_sidecar_timeout_seconds=5.0,
            moderation_sidecar_token="",
        ),
    )

    monkeypatch.setattr(
        moderation,
        "_sidecar_json_request",
        lambda endpoint, method, body, headers: {"ok": True} if endpoint == "/health" else None,
    )

    payload = moderation.get_moderation_sidecar_health()

    assert payload == {"moderation_sidecar": "up"}
