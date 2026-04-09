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


def test_store_content_addressed_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    stored_bytes: dict[str, bytes] = {}

    class _DummyMediaService:
        def exists(self, key: str) -> bool:
            return key in stored_bytes

        def put_bytes(
            self,
            key: str,
            content: bytes,
            content_type: str = "application/octet-stream",
        ) -> None:
            _ = content_type
            stored_bytes[key] = content

    def fake_get_media_service() -> _DummyMediaService:
        return _DummyMediaService()

    store_content_addressed = fanart._store_content_addressed  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    monkeypatch.setattr(fanart, "get_media_service", fake_get_media_service)

    rel1 = store_content_addressed(b"hello", " .AVIF ", "fanart/images")
    rel2 = store_content_addressed(b"hello", " .AVIF ", "fanart/images")

    assert rel1 == rel2
    assert stored_bytes[f"fanart/images/{rel1}"] == b"hello"


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

    saved_payloads: list[bytes] = []

    def fake_store(
        data: bytes,
        extension: str,
        media_prefix: str,
        *,
        upload_executor: object | None = None,
        pending_uploads: object | None = None,
    ) -> str:
        _ = (upload_executor, pending_uploads)
        saved_payloads.append(data)
        folder = "images" if media_prefix == "fanart/images" else "thumbs"
        return f"_objects/aa/{folder}.{extension}"

    created_items: list[dict[str, object]] = []

    def fake_create_fanart_item(
        *,
        item_id: str,
        uploader_username: str,
        title: str,
        summary: str,
        fandom: str = "",
        rating: str = "Not Rated",
        image_filename: str,
        thumb_filename: str | None,
        width: int | None,
        height: int | None,
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "item_id": item_id,
            "uploader_username": uploader_username,
            "title": title,
            "summary": summary,
            "fandom": fandom,
            "rating": rating,
            "image_filename": image_filename,
            "thumb_filename": thumb_filename,
            "width": width,
            "height": height,
        }
        created_items.append(item)
        return created_items[-1]

    captured_tag_sync: dict[str, str] = {
        "fanart_item_id": "",
        "fandom_csv": "",
        "freeform_csv": "",
    }

    def fake_replace_fanart_item_tags(
        fanart_item_id: str,
        *,
        fandom_csv: str = "",
        freeform_csv: str = "",
    ) -> None:
        captured_tag_sync["fanart_item_id"] = fanart_item_id
        captured_tag_sync["fandom_csv"] = fandom_csv
        captured_tag_sync["freeform_csv"] = freeform_csv

    def ensure_storage_dirs() -> None:
        return None

    def moderate_image(_path: Path) -> dict[str, bool | float]:
        return {"allow": True, "nsfw_score": 0.91}

    def suggested_rating_for_nsfw(_score: float) -> str:
        return "Explicit"

    def render_image_bytes(image: Image.Image, *, fmt: str, quality: int) -> bytes:
        _ = (image, fmt, quality)
        return b"avif"

    monkeypatch.setattr(fanart, "ensure_storage_dirs", ensure_storage_dirs)
    monkeypatch.setattr(fanart, "moderate_image", moderate_image)
    monkeypatch.setattr(fanart, "suggested_rating_for_nsfw", suggested_rating_for_nsfw)
    monkeypatch.setattr(fanart, "_store_content_addressed", fake_store)
    monkeypatch.setattr(fanart, "_render_image_bytes", render_image_bytes)
    monkeypatch.setattr(fanart, "create_fanart_item", fake_create_fanart_item)
    monkeypatch.setattr(fanart, "replace_fanart_item_tags", fake_replace_fanart_item_tags)

    result = fanart.ingest_fanart_image(
        image_path,
        uploader_username="alice",
        title=" Sunset ",
        summary=" Warm colors ",
        fandom="Skyverse",
        tags="clouds, horizon",
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
    assert result["tags"] == "clouds, horizon"
    assert captured_tag_sync["fanart_item_id"] == result["item_id"]
    assert captured_tag_sync["fandom_csv"] == "Skyverse"
    assert captured_tag_sync["freeform_csv"] == "clouds, horizon"
