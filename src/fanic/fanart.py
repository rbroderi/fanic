import hashlib
import uuid
from io import BytesIO
from pathlib import Path

import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
from PIL import Image
from PIL import UnidentifiedImageError

from fanic.ingest import ModerationBlockedError
from fanic.moderation import moderate_image
from fanic.moderation import suggested_rating_for_nsfw
from fanic.repository import create_fanart_item
from fanic.settings import FANART_DIR
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

_SETTINGS = get_settings()
IMAGE_AVIF_QUALITY = _SETTINGS.image_avif_quality
THUMBNAIL_AVIF_QUALITY = _SETTINGS.thumbnail_avif_quality
THUMBNAIL_MAX_DIMENSIONS = tuple(getattr(_SETTINGS, "thumbnail_max_dimensions", (720, 720)))
MAX_UPLOAD_IMAGE_PIXELS = int(getattr(_SETTINGS, "max_upload_image_pixels", 40000000))


def _render_image_bytes(image: Image.Image, *, fmt: str, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=quality)
    return buffer.getvalue()


def _prepare_image_for_avif(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA")
    return image.convert("RGB")


def _assert_image_pixels_within_limit(image: Image.Image, context: str) -> None:
    width, height = image.size
    total_pixels = int(width) * int(height)
    if total_pixels > MAX_UPLOAD_IMAGE_PIXELS:
        raise ValueError(f"{context} exceeds maximum allowed pixel count ({total_pixels} > {MAX_UPLOAD_IMAGE_PIXELS})")


def _normalize_rating(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        return "Not Rated"

    rating_aliases: dict[str, str] = {
        "g": "General Audiences",
        "general": "General Audiences",
        "general audiences": "General Audiences",
        "everyone": "General Audiences",
        "all ages": "General Audiences",
        "pg": "Teen And Up Audiences",
        "pg-13": "Teen And Up Audiences",
        "teen": "Teen And Up Audiences",
        "teen and up": "Teen And Up Audiences",
        "teen and up audiences": "Teen And Up Audiences",
        "t": "Teen And Up Audiences",
        "m": "Mature",
        "mature": "Mature",
        "r": "Mature",
        "explicit": "Explicit",
        "rule34": "Explicit",
        "rule 34": "Explicit",
        "r34": "Explicit",
        "nc-17": "Explicit",
        "x": "Explicit",
        "not rated": "Not Rated",
        "nr": "Not Rated",
        "unrated": "Not Rated",
    }

    return rating_aliases.get(normalized, value.strip())


def _elevate_rating(current: str, suggested: str | None) -> str:
    normalized_current = _normalize_rating(current)
    normalized_suggested = _normalize_rating(suggested if suggested else "")
    if normalized_suggested == "Explicit" and normalized_current != "Explicit":
        return "Explicit"
    return normalized_current


def _content_addressed_rel_path(data: bytes, extension: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    normalized_ext = extension.strip().lower().lstrip(".")
    resolved_ext = normalized_ext if normalized_ext else "bin"
    return f"_objects/{digest[:2]}/{digest}.{resolved_ext}"


def _store_content_addressed(base_dir: Path, data: bytes, extension: str) -> str:
    rel_path = _content_addressed_rel_path(data, extension)
    target = (base_dir / rel_path).resolve()
    resolved_base = base_dir.resolve()
    try:
        _ = target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Upload target escapes fanart storage: {target}") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return rel_path

    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        pass
    return rel_path


def ingest_fanart_image(
    image_path: Path,
    *,
    uploader_username: str,
    title: str,
    summary: str,
    fandom: str = "",
    rating: str = "Not Rated",
) -> dict[str, object]:
    ensure_storage_dirs()

    normalized_uploader = uploader_username.strip()
    if not normalized_uploader:
        raise ValueError("uploader_username must not be empty")
    normalized_rating = _normalize_rating(rating)

    image_path = image_path.resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    moderation = moderate_image(str(image_path))
    if not moderation["allow"]:
        raise ModerationBlockedError(dict(moderation))
    rating_before = normalized_rating
    normalized_rating = _elevate_rating(
        normalized_rating,
        suggested_rating_for_nsfw(float(moderation["nsfw_score"])),
    )

    images_dir = FANART_DIR / "images"
    thumbs_dir = FANART_DIR / "thumbs"
    images_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    width: int | None = None
    height: int | None = None
    try:
        with Image.open(image_path) as image:
            _assert_image_pixels_within_limit(image, "Uploaded fanart image")
            width, height = image.size

            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=int(IMAGE_AVIF_QUALITY),
            )
            image_name = _store_content_addressed(images_dir, page_bytes, "avif")

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail(THUMBNAIL_MAX_DIMENSIONS)
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="AVIF",
                quality=int(THUMBNAIL_AVIF_QUALITY),
            )
            thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "avif")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert fanart image") from exc

    item_id = uuid.uuid4().hex[:12]
    _ = create_fanart_item(
        item_id=item_id,
        uploader_username=normalized_uploader,
        title=title.strip(),
        summary=summary.strip(),
        fandom=fandom.strip(),
        rating=normalized_rating,
        image_filename=image_name,
        thumb_filename=thumb_name,
        width=width,
        height=height,
    )

    return {
        "item_id": item_id,
        "uploader_username": normalized_uploader,
        "image_filename": image_name,
        "thumb_filename": thumb_name,
        "fandom": fandom.strip(),
        "rating": normalized_rating,
        "rating_before": rating_before,
        "rating_after": normalized_rating,
        "rating_auto_elevated": normalized_rating != rating_before,
        "width": width,
        "height": height,
    }
