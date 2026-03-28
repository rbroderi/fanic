from pathlib import Path

import pytest

from fanic.moderation import moderate_image
from fanic.moderation import suggested_rating_for_nsfw

MEDIA_DIR = Path(__file__).resolve().parent / "media"


@pytest.mark.parametrize(
    ("filename", "expected_allow", "expected_style"),
    [
        ("safe.png", True, "comic"),
        ("explicit.jpg", True, "comic"),
        ("photorealistic.jpg", False, "photorealistic"),
        ("photorealistic_marvel.jpg", False, "photorealistic"),
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

    result = moderate_image(str(image_path))

    assert result["path"] == str(image_path)
    assert result["allow"] is expected_allow
    assert result["style"] == expected_style

    if expected_allow:
        assert isinstance(result["nsfw_score"], float)
        assert result["reasons"] == []
    else:
        assert result["nsfw_score"] == 0.0
        assert any("photorealistic image" in reason for reason in result["reasons"])


def test_moderation_media_explicit_and_safe_rating_suggestion() -> None:
    explicit_path = MEDIA_DIR / "explicit.jpg"
    safe_path = MEDIA_DIR / "safe.png"

    if not explicit_path.exists() or not safe_path.exists():
        pytest.skip("Missing one or more rating fixtures")

    explicit_result = moderate_image(str(explicit_path))
    safe_result = moderate_image(str(safe_path))

    explicit_suggested = suggested_rating_for_nsfw(explicit_result["nsfw_score"])
    safe_suggested = suggested_rating_for_nsfw(safe_result["nsfw_score"])

    assert explicit_result["allow"] is True
    assert safe_result["allow"] is True
    assert explicit_suggested == "Explicit"
    assert safe_suggested is None
