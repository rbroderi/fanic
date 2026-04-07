import json
from pathlib import Path

import pytest

from fanic.moderation import ModerationResult
from fanic.moderation import moderate_image_local
from fanic.moderation import suggested_rating_for_nsfw

MEDIA_DIR = Path(__file__).resolve().parent / "media"


def _moderation_stats_text(result: ModerationResult) -> str:
    payload = {
        "path": result.get("path"),
        "allow": result.get("allow"),
        "style": result.get("style"),
        "nsfw_score": result.get("nsfw_score"),
        "reasons": result.get("reasons"),
        "style_confidences": result.get("style_confidences"),
        "nsfw_confidences": result.get("nsfw_confidences"),
        "style_debug": result.get("style_debug"),
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


@pytest.mark.parametrize(
    ("filename", "expected_allow", "expected_style"),
    [
        ("safe.png", True, "comic"),
        ("safe2.webp", True, "comic"),
        ("safe3.avif", True, "comic"),
        ("safe-marvel.jpg", True, "comic"),
        ("explicit.jpg", True, "comic"),
        ("photorealistic.jpg", False, "photorealistic"),
        ("photorealistic-marvel.avif", False, "photorealistic"),
    ],
)
def test_moderation_media_expected_outcomes(
    filename: str,
    expected_allow: bool,
    expected_style: str,
) -> None:
    image_path = MEDIA_DIR / filename
    if not image_path.exists():
        pytest.skip(f"Missing fixture: {image_path.name}")

    result = moderate_image_local(str(image_path))
    stats_text = _moderation_stats_text(result)

    assert result["path"] == str(image_path), stats_text
    assert result["allow"] is expected_allow, stats_text
    assert result["style"] == expected_style, stats_text

    if expected_allow:
        assert isinstance(result["nsfw_score"], float), stats_text
        assert result["reasons"] == [], stats_text
    else:
        assert result["nsfw_score"] == 0.0, stats_text
        assert any("photorealistic image" in reason for reason in result["reasons"]), stats_text


def test_moderation_media_explicit_and_safe_rating_suggestion() -> None:
    explicit_path = MEDIA_DIR / "explicit.jpg"
    safe_path = MEDIA_DIR / "safe.png"
    safe2_path = MEDIA_DIR / "safe2.webp"

    if not explicit_path.exists() or not safe_path.exists() or not safe2_path.exists():
        pytest.skip("Missing one or more rating fixtures")

    explicit_result = moderate_image_local(str(explicit_path))
    safe_result = moderate_image_local(str(safe_path))
    safe2_result = moderate_image_local(str(safe2_path))
    explicit_stats = _moderation_stats_text(explicit_result)
    safe_stats = _moderation_stats_text(safe_result)
    safe2_stats = _moderation_stats_text(safe2_result)

    explicit_suggested = suggested_rating_for_nsfw(explicit_result["nsfw_score"])
    safe_suggested = suggested_rating_for_nsfw(safe_result["nsfw_score"])
    safe2_suggested = suggested_rating_for_nsfw(safe2_result["nsfw_score"])

    assert explicit_result["allow"] is True, explicit_stats
    assert safe_result["allow"] is True, safe_stats
    assert safe2_result["allow"] is True, safe2_stats
    assert explicit_suggested == "Explicit", explicit_stats
    assert safe_suggested is None, safe_stats
    assert safe2_suggested is None, safe2_stats


@pytest.mark.parametrize(
    "filename",
    [
        "safe.png",
        "safe2.webp",
        "safe3.avif",
        "safe-marvel.jpg",
        "explicit.jpg",
    ],
)
def test_moderation_media_sfw_and_explicit_confidences_are_non_zero(
    filename: str,
) -> None:
    image_path = MEDIA_DIR / filename
    if not image_path.exists():
        pytest.skip(f"Missing fixture: {image_path.name}")

    result = moderate_image_local(str(image_path))
    stats_text = _moderation_stats_text(result)

    assert result["allow"] is True, stats_text
    confidences = result["nsfw_confidences"]
    assert isinstance(confidences, dict), stats_text

    sfw_score = confidences.get("sfw")
    explicit_score = confidences.get("explicit")
    assert isinstance(sfw_score, float), stats_text
    assert isinstance(explicit_score, float), stats_text
    assert sfw_score != 0.0, stats_text
    assert explicit_score != 0.0, stats_text
