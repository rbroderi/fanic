from types import SimpleNamespace

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
    monkeypatch.setattr(moderation, "_NSFW_DETECTOR", fake)
    monkeypatch.setattr(moderation, "_STYLE_CLASSIFIER", fake)

    result = moderation.initialize_moderation_models(force=True)

    assert result == {
        "requested": True,
        "nsfw_ready": True,
        "style_ready": True,
    }
    assert init_calls == ["nsfw", "style"]
