import base64
import hashlib
import logging
import uuid
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
from io import BytesIO
from pathlib import Path
from typing import cast

import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
from PIL import Image
from PIL import UnidentifiedImageError

from fanic.ingest import ModerationBlockedError
from fanic.media import get_media_service
from fanic.moderation import get_explicit_max_threshold
from fanic.moderation import get_explicit_threshold
from fanic.moderation import get_style_max_confidence_photorealistic
from fanic.moderation import moderate_image
from fanic.moderation import suggested_rating_for_nsfw
from fanic.remote_mod_moderation import graphic_violence_manual_review_confidence
from fanic.remote_mod_moderation import moderate_content_with_remote_mod
from fanic.remote_mod_moderation import remote_mod_confidence_levels
from fanic.remote_mod_moderation import suggested_rating_for_remote_mod_result
from fanic.repository.fanart import create_fanart_item
from fanic.repository.fanart import replace_fanart_item_tags
from fanic.repository.moderation_queue import enqueue_moderation_review
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

_SETTINGS = get_settings()
THUMBNAIL_MAX_DIMENSIONS = _SETTINGS.thumbnail_max_dimensions
IMAGE_AVIF_QUALITY = _SETTINGS.image_avif_quality
THUMBNAIL_AVIF_QUALITY = _SETTINGS.thumbnail_avif_quality
MAX_UPLOAD_IMAGE_PIXELS = _SETTINGS.max_upload_image_pixels
_BUNNY_SKIP_EXISTS_CHECK = (
    True if (_SETTINGS.media_backend.strip().lower() == "bunny" and _SETTINGS.media_bunny_skip_exists_check) else False
)
_BUNNY_UPLOAD_WORKERS = (
    _SETTINGS.media_bunny_upload_workers if _SETTINGS.media_backend.strip().lower() == "bunny" else 1
)
_LOGGER = logging.getLogger("fanic.fanart")

_IMAGE_SUFFIX_TO_MIME: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".gif": "image/gif",
}


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
    rank = {
        "Not Rated": 0,
        "General Audiences": 1,
        "Teen And Up Audiences": 2,
        "Mature": 3,
        "Explicit": 4,
    }
    current_rank = rank.get(normalized_current, 0)
    suggested_rank = rank.get(normalized_suggested, 0)
    if suggested_rank > current_rank:
        return normalized_suggested
    return normalized_current


def _remote_mod_assessment_for_path(image_path: Path) -> dict[str, object]:
    mime_type = _IMAGE_SUFFIX_TO_MIME.get(image_path.suffix.lower(), "image/jpeg")
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    image_data_url = f"data:{mime_type};base64,{image_b64}"
    payload = moderate_content_with_remote_mod(image_url=image_data_url)
    confidences = remote_mod_confidence_levels(payload)
    return {
        "suggested_rating": suggested_rating_for_remote_mod_result(payload),
        "graphic_violence_manual_review_confidence": (graphic_violence_manual_review_confidence(payload)),
        "graphic_violence_confidence": float(confidences.get("graphic_violence_confidence", 0.0)),
        "payload": payload,
    }


def _content_addressed_rel_path(data: bytes, extension: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    normalized_ext = extension.strip().lower().lstrip(".")
    resolved_ext = normalized_ext if normalized_ext else "bin"
    return f"_objects/{digest[:2]}/{digest}.{resolved_ext}"


def _upload_media_key(media_key: str, data: bytes) -> None:
    media_service = get_media_service()
    if _BUNNY_SKIP_EXISTS_CHECK:
        media_service.put_bytes(media_key, data, content_type="image/avif")
        return
    if not media_service.exists(media_key):
        media_service.put_bytes(media_key, data, content_type="image/avif")


def _store_content_addressed(
    data: bytes,
    extension: str,
    media_prefix: str,
    *,
    upload_executor: ThreadPoolExecutor | None = None,
    pending_uploads: set[Future[None]] | None = None,
) -> str:
    rel_path = _content_addressed_rel_path(data, extension)
    media_service = get_media_service()
    media_key = f"{media_prefix.strip().strip('/')}/{rel_path}"

    if upload_executor is not None and pending_uploads is not None:
        future = upload_executor.submit(_upload_media_key, media_key, data)
        pending_uploads.add(future)
        return rel_path

    if _BUNNY_SKIP_EXISTS_CHECK:
        media_service.put_bytes(media_key, data, content_type="image/avif")
        return rel_path

    if not media_service.exists(media_key):
        media_service.put_bytes(media_key, data, content_type="image/avif")
    return rel_path


def ingest_fanart_image(
    image_path: Path,
    *,
    uploader_username: str,
    title: str,
    summary: str,
    fandom: str = "",
    tags: str = "",
    rating: str = "Not Rated",
) -> dict[str, object]:
    ensure_storage_dirs()

    normalized_uploader = uploader_username.strip()
    if not normalized_uploader:
        raise ValueError("uploader_username must not be empty")
    normalized_rating = _normalize_rating(rating)
    normalized_summary = summary.strip()
    normalized_tags = ", ".join(part.strip() for part in tags.split(",") if part.strip())

    image_path = image_path.resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    moderation = moderate_image(str(image_path))
    if not moderation["allow"]:
        raise ModerationBlockedError(dict(moderation))
    rating_before = normalized_rating
    remote_rating_suggestion: str | None = None
    remote_graphic_review_confidence: float | None = None
    remote_graphic_confidence = 0.0
    remote_payload: dict[str, object] = {}
    try:
        remote_assessment = _remote_mod_assessment_for_path(image_path)
        remote_rating_suggestion = str(
            remote_assessment.get("suggested_rating") if remote_assessment.get("suggested_rating") else ""
        ).strip()
        remote_graphic_review_obj = remote_assessment.get("graphic_violence_manual_review_confidence")
        if isinstance(remote_graphic_review_obj, (int, float)):
            remote_graphic_review_confidence = float(remote_graphic_review_obj)
        remote_graphic_conf_obj = remote_assessment.get("graphic_violence_confidence", 0.0)
        if isinstance(remote_graphic_conf_obj, (int, float)):
            remote_graphic_confidence = float(remote_graphic_conf_obj)
        payload_obj = remote_assessment.get("payload")
        if isinstance(payload_obj, dict):
            remote_payload = {str(key): value for key, value in cast(dict[object, object], payload_obj).items()}
        else:
            remote_payload = {}
    except Exception:
        _LOGGER.exception("Remote moderation rating suggestion failed for fanart upload")

    normalized_rating = _elevate_rating(
        normalized_rating,
        remote_rating_suggestion
        if remote_rating_suggestion
        else suggested_rating_for_nsfw(float(moderation["nsfw_score"])),
    )

    width: int | None = None
    height: int | None = None
    upload_executor: ThreadPoolExecutor | None = None
    try:
        pending_uploads: set[Future[None]] = set()
        if _BUNNY_UPLOAD_WORKERS > 1:
            upload_executor = ThreadPoolExecutor(
                max_workers=min(_BUNNY_UPLOAD_WORKERS, 2),
                thread_name_prefix="fanic-fanart-upload",
            )

        with Image.open(image_path) as image:
            _assert_image_pixels_within_limit(image, "Uploaded fanart image")
            width, height = image.size

            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=int(IMAGE_AVIF_QUALITY),
            )
            image_name = _store_content_addressed(
                page_bytes,
                "avif",
                "fanart/images",
                upload_executor=upload_executor,
                pending_uploads=pending_uploads,
            )

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail(THUMBNAIL_MAX_DIMENSIONS)
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="AVIF",
                quality=int(THUMBNAIL_AVIF_QUALITY),
            )
            thumb_name = _store_content_addressed(
                thumb_bytes,
                "avif",
                "fanart/thumbs",
                upload_executor=upload_executor,
                pending_uploads=pending_uploads,
            )

        if pending_uploads:
            done, _ = wait(pending_uploads)
            for finished in done:
                finished.result()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert fanart image") from exc
    finally:
        if upload_executor is not None:
            upload_executor.shutdown(wait=True)

    item_id = uuid.uuid4().hex[:12]
    _ = create_fanart_item(
        item_id=item_id,
        uploader_username=normalized_uploader,
        title=title.strip(),
        summary=normalized_summary,
        fandom=fandom.strip(),
        rating=normalized_rating,
        image_filename=image_name,
        thumb_filename=thumb_name,
        width=width,
        height=height,
    )
    replace_fanart_item_tags(
        item_id,
        fandom_csv=fandom.strip(),
        freeform_csv=normalized_tags,
    )
    if bool(moderation.get("manual_review_required", False)):
        reason_type = str(moderation.get("manual_review_reason", "")).strip()
        if reason_type:
            enqueue_moderation_review(
                content_type="fanart",
                content_id=item_id,
                uploader_username=normalized_uploader,
                reason_type=reason_type,
                confidence=float(moderation.get("manual_review_confidence", 0.0)),
                min_threshold=(
                    _SETTINGS.style_min_confidence_photorealistic
                    if reason_type == "photorealistic"
                    else get_explicit_threshold()
                ),
                max_threshold=(
                    get_style_max_confidence_photorealistic()
                    if reason_type == "photorealistic"
                    else get_explicit_max_threshold()
                ),
                moderation_payload={str(key): value for key, value in moderation.items()},
            )
    if remote_graphic_review_confidence is not None:
        enqueue_moderation_review(
            content_type="fanart",
            content_id=item_id,
            uploader_username=normalized_uploader,
            reason_type="graphic-violence",
            confidence=remote_graphic_review_confidence,
            min_threshold=float(_SETTINGS.graphic_violence_min_threshold),
            max_threshold=float(_SETTINGS.graphic_violence_max_threshold),
            moderation_payload={
                "remote_mod": remote_payload,
                "graphic_violence_confidence": remote_graphic_confidence,
            },
        )
    manual_review_reason = str(moderation.get("manual_review_reason", "")).strip()
    if (not manual_review_reason) and remote_graphic_review_confidence is not None:
        manual_review_reason = "graphic-violence"
    manual_review_queued = bool(moderation.get("manual_review_required", False)) or (
        remote_graphic_review_confidence is not None
    )

    return {
        "item_id": item_id,
        "uploader_username": normalized_uploader,
        "image_filename": image_name,
        "thumb_filename": thumb_name,
        "fandom": fandom.strip(),
        "tags": normalized_tags,
        "summary": normalized_summary,
        "rating": normalized_rating,
        "rating_before": rating_before,
        "rating_after": normalized_rating,
        "rating_auto_elevated": normalized_rating != rating_before,
        "manual_review_queued": manual_review_queued,
        "manual_review_reason": manual_review_reason,
        "explicit_min_threshold": get_explicit_threshold(),
        "explicit_max_threshold": get_explicit_max_threshold(),
        "width": width,
        "height": height,
    }
