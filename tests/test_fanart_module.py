from pathlib import Path

import pytest
from PIL import Image

import fanic.fanart as fanart
from fanic.ingest import ModerationBlockedError


def _write_png(path: Path, size: tuple[int, int] = (16, 16)) -> None:
    image = Image.new("RGB", size, color=(255, 0, 0))
    image.save(path, format="PNG")


def test_rating_helpers_normalize_and_elevate() -> None:
    normalize_rating = fanart._normalize_rating  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    elevate_rating = fanart._elevate_rating  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    assert normalize_rating("pg-13") == "Teen And Up Audiences"
    assert normalize_rating(" ") == "Not Rated"
    assert elevate_rating("Teen And Up Audiences", "Explicit") == "Explicit"
    assert elevate_rating("Explicit", "Mature") == "Explicit"


def test_image_pixel_limit_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fanart, "MAX_UPLOAD_IMAGE_PIXELS", 4)
    assert_image_pixels_within_limit = fanart._assert_image_pixels_within_limit  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    with Image.new("RGB", (3, 3)) as image:
        with pytest.raises(ValueError, match="exceeds maximum allowed pixel count"):
            assert_image_pixels_within_limit(image, "Uploaded fanart image")


def test_store_content_addressed_is_idempotent(tmp_path: Path) -> None:
    base_dir = tmp_path / "fanart" / "images"
    base_dir.mkdir(parents=True, exist_ok=True)

    store_content_addressed = fanart._store_content_addressed  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    rel1 = store_content_addressed(base_dir, b"hello", " .AVIF ")
    rel2 = store_content_addressed(base_dir, b"hello", " .AVIF ")

    assert rel1 == rel2
    assert (base_dir / rel1).read_bytes() == b"hello"


def test_ingest_fanart_image_requires_uploader(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    _write_png(image_path)

    with pytest.raises(ValueError, match="uploader_username must not be empty"):
        fanart.ingest_fanart_image(
            image_path,
            uploader_username="   ",
            title="Title",
            summary="Summary",
        )


def test_ingest_fanart_image_missing_path_raises(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.png"

    with pytest.raises(FileNotFoundError, match="Image not found"):
        fanart.ingest_fanart_image(
            missing_path,
            uploader_username="alice",
            title="Title",
            summary="Summary",
        )


def test_ingest_fanart_image_moderation_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    _write_png(image_path)

    def ensure_storage_dirs() -> None:
        return None

    def moderate_image(_path: Path) -> dict[str, bool | float | str]:
        return {
            "allow": False,
            "nsfw_score": 0.95,
            "reasons": "explicit",
        }

    monkeypatch.setattr(fanart, "ensure_storage_dirs", ensure_storage_dirs)
    monkeypatch.setattr(
        fanart,
        "moderate_image",
        moderate_image,
    )

    with pytest.raises(ModerationBlockedError):
        fanart.ingest_fanart_image(
            image_path,
            uploader_username="alice",
            title="Title",
            summary="Summary",
        )


def test_ingest_fanart_image_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page.png"
    _write_png(image_path, size=(20, 10))

    fanart_root = tmp_path / "fanart"
    (fanart_root / "images").mkdir(parents=True, exist_ok=True)
    (fanart_root / "thumbs").mkdir(parents=True, exist_ok=True)

    saved_payloads: list[bytes] = []

    def fake_store(base_dir: Path, data: bytes, extension: str) -> str:
        saved_payloads.append(data)
        folder = "images" if base_dir.name == "images" else "thumbs"
        return f"_objects/aa/{folder}.{extension}"

    created_items: list[dict[str, object]] = []

    def fake_create_fanart_item(**kwargs: object) -> dict[str, object]:
        created_items.append(dict(kwargs))
        return created_items[-1]

    def ensure_storage_dirs() -> None:
        return None

    def moderate_image(_path: Path) -> dict[str, bool | float]:
        return {"allow": True, "nsfw_score": 0.91}

    def suggested_rating_for_nsfw(_score: float) -> str:
        return "Explicit"

    def render_image_bytes(*_args: object, **_kwargs: object) -> bytes:
        return b"avif"

    monkeypatch.setattr(fanart, "ensure_storage_dirs", ensure_storage_dirs)
    monkeypatch.setattr(fanart, "FANART_DIR", fanart_root)
    monkeypatch.setattr(fanart, "moderate_image", moderate_image)
    monkeypatch.setattr(fanart, "suggested_rating_for_nsfw", suggested_rating_for_nsfw)
    monkeypatch.setattr(fanart, "_store_content_addressed", fake_store)
    monkeypatch.setattr(fanart, "_render_image_bytes", render_image_bytes)
    monkeypatch.setattr(fanart, "create_fanart_item", fake_create_fanart_item)

    result = fanart.ingest_fanart_image(
        image_path,
        uploader_username="alice",
        title=" Sunset ",
        summary=" Warm colors ",
        fandom="Skyverse",
        rating="Teen",
    )

    assert result["uploader_username"] == "alice"
    assert result["rating_before"] == "Teen And Up Audiences"
    assert result["rating_after"] == "Explicit"
    assert result["rating_auto_elevated"] is True
    assert result["width"] == 20
    assert result["height"] == 10
    assert len(saved_payloads) == 2
    assert len(created_items) == 1
    assert created_items[0]["title"] == "Sunset"
    assert created_items[0]["summary"] == "Warm colors"
