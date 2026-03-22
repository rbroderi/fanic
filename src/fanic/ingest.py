from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import cast
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
from PIL import Image, UnidentifiedImageError
from tqdm import tqdm

from fanic.moderation import (
    get_explicit_threshold,
    moderate_image,
    moderate_image_bytes,
    suggested_rating_for_nsfw,
)
from fanic.paths import CBZ_DIR, WORKS_DIR, ensure_storage_dirs
from fanic.repository import (
    add_work_chapter,
    create_work_version_snapshot,
    delete_work_chapter,
    get_work,
    list_work_chapter_members,
    list_work_chapters,
    list_work_page_image_names,
    list_work_page_rows,
    replace_work_chapter_members,
    replace_work_pages,
    replace_work_tags,
    update_work_chapter,
    upsert_work,
)
from fanic.utils import slugify

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
AVIF_QUALITY = 60

_RATING_RANK = {
    "Not Rated": 0,
    "General Audiences": 1,
    "Teen And Up Audiences": 2,
    "Mature": 3,
    "Explicit": 4,
}

type ComicInfoValue = str | list[str]
type ComicInfoMetadata = dict[str, ComicInfoValue]


def _render_image_bytes(image: Image.Image, *, fmt: str, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=quality)
    return buffer.getvalue()


def _content_addressed_rel_path(data: bytes, extension: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    normalized_ext = extension.strip().lower().lstrip(".") or "bin"
    return f"_objects/{digest[:2]}/{digest}.{normalized_ext}"


def _store_content_addressed(base_dir: Path, data: bytes, extension: str) -> str:
    rel_path = _content_addressed_rel_path(data, extension)
    target = base_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return rel_path

    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        # Another request wrote the same hash concurrently.
        pass
    return rel_path


class ModerationBlockedError(ValueError):
    moderation: dict[str, object]

    def __init__(self, moderation: dict[str, object]) -> None:
        reasons_obj = moderation.get("reasons")
        reasons: list[str] = []
        if isinstance(reasons_obj, str):
            reasons = [reasons_obj]
        elif reasons_obj is not None:
            reasons = [str(reasons_obj)]

        reason_text = "; ".join(reasons) if reasons else "blocked by moderation"
        super().__init__(f"Blocked image: {reason_text}")
        self.moderation = moderation


def _prepare_image_for_avif(image: Image.Image) -> Image.Image:
    # AVIF expects RGB/RGBA-like pixel data; normalize uncommon modes.
    if image.mode in {"RGBA", "LA"}:
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA")
    return image.convert("RGB")


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _comma_split(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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


def _elevate_rating(current: object, suggested: str | None) -> str:
    normalized_current = _normalize_rating(str(current or "Not Rated"))
    if not suggested:
        return normalized_current
    normalized_suggested = _normalize_rating(suggested)
    if _RATING_RANK.get(normalized_suggested, 0) > _RATING_RANK.get(
        normalized_current, 0
    ):
        return normalized_suggested
    return normalized_current


def _clean_xml_value(value: str | None) -> str:
    return (value or "").strip()


def parse_comicinfo_xml(xml_text: str) -> ComicInfoMetadata:
    metadata: ComicInfoMetadata = {}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return metadata

    title = _clean_xml_value(root.findtext("Title"))
    if title:
        metadata["title"] = title

    summary = _clean_xml_value(root.findtext("Summary"))
    if summary:
        metadata["summary"] = summary

    language = _clean_xml_value(root.findtext("LanguageISO"))
    if language:
        metadata["language"] = language

    series = _clean_xml_value(root.findtext("Series"))
    if series:
        metadata["series"] = series
        metadata["fandoms"] = [series]

    series_index = _clean_xml_value(root.findtext("Number"))
    if series_index:
        metadata["series_index"] = series_index

    characters = _comma_split(_clean_xml_value(root.findtext("Characters")))
    if characters:
        metadata["characters"] = characters

    tags = _comma_split(_clean_xml_value(root.findtext("Tags")))
    if tags:
        metadata["freeform_tags"] = tags

    age_rating = _clean_xml_value(root.findtext("AgeRating"))
    if age_rating:
        metadata["rating"] = _normalize_rating(age_rating)

    year = _clean_xml_value(root.findtext("Year"))
    month = _clean_xml_value(root.findtext("Month"))
    day = _clean_xml_value(root.findtext("Day"))
    if year:
        month_value = month.zfill(2) if month else "01"
        day_value = day.zfill(2) if day else "01"
        metadata["published_at"] = f"{year}-{month_value}-{day_value}"

    return metadata


def extract_comicinfo_metadata_from_cbz(cbz_path: Path) -> ComicInfoMetadata:
    cbz_path = cbz_path.resolve()
    if not cbz_path.exists():
        return {}

    with ZipFile(cbz_path) as zip_file:
        candidates = [
            member
            for member in zip_file.namelist()
            if member.lower().endswith("comicinfo.xml")
        ]
        if not candidates:
            return {}

        xml_text = zip_file.read(candidates[0]).decode("utf-8", errors="replace")
        return parse_comicinfo_xml(xml_text)


def _load_metadata_from_comicinfo(zip_file: ZipFile) -> ComicInfoMetadata:
    candidates = [
        member
        for member in zip_file.namelist()
        if member.lower().endswith("comicinfo.xml")
    ]
    if not candidates:
        return {}

    xml_text = zip_file.read(candidates[0]).decode("utf-8", errors="replace")
    return parse_comicinfo_xml(xml_text)


def _is_image_member_name(member: str) -> bool:
    suffix = Path(member).suffix.lower()
    return suffix in {
        *SUPPORTED_IMAGE_EXTENSIONS,
        ".bmp",
        ".tif",
        ".tiff",
        ".jfif",
    }


def _looks_like_image_bytes(data: bytes) -> bool:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


def ingest_cbz(
    cbz_path: Path,
    metadata_override_path: Path | None = None,
    uploader_username: str | None = None,
    *,
    show_progress: bool = False,
    progress_desc: str = "Ingesting CBZ pages",
    progress_hook: Callable[[str, str, int, int], None] | None = None,
) -> dict[str, object]:
    ensure_storage_dirs()
    cbz_path = cbz_path.resolve()
    if not cbz_path.exists():
        raise FileNotFoundError(f"CBZ not found: {cbz_path}")

    with ZipFile(cbz_path) as zip_file:
        if progress_hook is not None:
            progress_hook("read-metadata", "Reading metadata", 0, 0)
        metadata: dict[str, object] = {
            key: value for key, value in _load_metadata_from_comicinfo(zip_file).items()
        }
        if metadata_override_path:
            override_obj = json.loads(
                metadata_override_path.read_text(encoding="utf-8")
            )
            if isinstance(override_obj, Mapping):
                override_map = cast(Mapping[object, object], override_obj)
                normalized_override: dict[str, object] = {}
                for key, value in override_map.items():
                    normalized_override[str(key)] = value
                metadata.update(normalized_override)

        title = str(metadata.get("title") or cbz_path.stem)
        work_id = str(metadata.get("id") or uuid.uuid4().hex[:12])
        slug = str(metadata.get("slug") or slugify(title))

        work_dir = WORKS_DIR / work_id
        pages_dir = work_dir / "pages"
        thumbs_dir = work_dir / "thumbs"
        work_dir.mkdir(parents=True, exist_ok=True)
        pages_dir.mkdir(parents=True, exist_ok=True)
        thumbs_dir.mkdir(parents=True, exist_ok=True)

        candidate_members = [
            member
            for member in zip_file.namelist()
            if member and not member.endswith("/")
        ]

        image_members = [
            member for member in candidate_members if _is_image_member_name(member)
        ]

        # Some CBZ files contain page images with missing/odd extensions.
        if not image_members:
            for member in candidate_members:
                if member.lower().endswith("comicinfo.xml"):
                    continue
                extracted = zip_file.read(member)
                if _looks_like_image_bytes(extracted):
                    image_members.append(member)

        if not image_members:
            raise ValueError(
                "CBZ contains no recognizable image pages. "
                "Supported extensions include: "
                f"{', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}, .bmp, .tif, .tiff, .jfif"
            )

        configured_order_raw = metadata.get("page_order", [])
        configured_order: list[str] = []
        if isinstance(configured_order_raw, Sequence) and not isinstance(
            configured_order_raw,
            (str, bytes),
        ):
            for name in configured_order_raw:
                configured_order.append(str(name))
        if configured_order:
            image_members = sorted(
                image_members,
                key=lambda name: (
                    configured_order.index(Path(name).name)
                    if Path(name).name in configured_order
                    else 999999
                ),
            )
        else:
            image_members = sorted(image_members)

        if progress_hook is not None:
            progress_hook(
                "prepare-pages",
                "Preparing pages",
                0,
                len(image_members),
            )

        pages: list[dict[str, object]] = []
        max_nsfw_score = 0.0
        member_iter: object = image_members
        progress = None
        if show_progress:
            progress = tqdm(
                image_members,
                desc=progress_desc,
                unit="page",
                leave=True,
            )
            member_iter = progress

        try:
            for index, member in enumerate(member_iter, start=1):
                if progress_hook is not None:
                    progress_hook(
                        "moderate",
                        f"Moderating page {index}/{len(image_members)}",
                        index,
                        len(image_members),
                    )
                if progress is not None:
                    progress.set_postfix_str("moderate")
                extracted = zip_file.read(member)
                moderation = moderate_image_bytes(extracted, suffix=Path(member).suffix)
                if not moderation["allow"]:
                    moderation_payload = dict(moderation)
                    moderation_payload["source_member"] = member
                    raise ModerationBlockedError(moderation_payload)
                max_nsfw_score = max(max_nsfw_score, moderation["nsfw_score"])

                width = None
                height = None
                try:
                    if progress is not None:
                        progress.set_postfix_str("decode")
                    if progress_hook is not None:
                        progress_hook(
                            "decode",
                            f"Decoding page {index}/{len(image_members)}",
                            index,
                            len(image_members),
                        )
                    with Image.open(BytesIO(extracted)) as image:
                        width, height = image.size

                        if progress is not None:
                            progress.set_postfix_str("encode-page")
                        if progress_hook is not None:
                            progress_hook(
                                "encode-page",
                                f"Encoding page {index}/{len(image_members)}",
                                index,
                                len(image_members),
                            )
                        page_image = _prepare_image_for_avif(image)
                        page_bytes = _render_image_bytes(
                            page_image,
                            fmt="AVIF",
                            quality=AVIF_QUALITY,
                        )

                        if progress is not None:
                            progress.set_postfix_str("store-page")
                        if progress_hook is not None:
                            progress_hook(
                                "store-page",
                                f"Storing page {index}/{len(image_members)}",
                                index,
                                len(image_members),
                            )
                        image_name = _store_content_addressed(
                            pages_dir,
                            page_bytes,
                            "avif",
                        )

                        if progress is not None:
                            progress.set_postfix_str("encode-thumb")
                        if progress_hook is not None:
                            progress_hook(
                                "encode-thumb",
                                f"Encoding thumbnail {index}/{len(image_members)}",
                                index,
                                len(image_members),
                            )
                        thumb_image = _prepare_image_for_avif(image)
                        thumb_image.thumbnail((360, 360))
                        thumb_bytes = _render_image_bytes(
                            thumb_image,
                            fmt="WEBP",
                            quality=82,
                        )

                        if progress is not None:
                            progress.set_postfix_str("store-thumb")
                        if progress_hook is not None:
                            progress_hook(
                                "store-thumb",
                                f"Storing thumbnail {index}/{len(image_members)}",
                                index,
                                len(image_members),
                            )
                        thumb_name = _store_content_addressed(
                            thumbs_dir,
                            thumb_bytes,
                            "webp",
                        )
                except (UnidentifiedImageError, OSError, ValueError) as exc:
                    raise ValueError(
                        f"Failed to convert page to AVIF: {member}"
                    ) from exc

                pages.append(
                    {
                        "page_index": index,
                        "image_filename": image_name,
                        "thumb_filename": thumb_name,
                        "width": width,
                        "height": height,
                    }
                )
        finally:
            if progress is not None:
                progress.set_postfix_str("done")
                progress.close()

        rating_before = _normalize_rating(str(metadata.get("rating", "Not Rated")))
        rating_after = _elevate_rating(
            metadata.get("rating", "Not Rated"),
            suggested_rating_for_nsfw(max_nsfw_score),
        )
        metadata["rating"] = rating_after

    cover_page_raw = metadata.get("cover_page_index", 1)
    cover_page_index = (
        int(cover_page_raw) if isinstance(cover_page_raw, (int, str)) else 1
    )

    work: dict[str, object] = {
        "id": work_id,
        "slug": slug,
        "title": title,
        "summary": metadata.get("summary", ""),
        "rating": metadata.get("rating", "Not Rated"),
        "warnings": metadata.get("warnings", "No Archive Warnings Apply"),
        "language": metadata.get("language", "en"),
        "status": metadata.get("status", "in_progress"),
        "creators": metadata.get("creators", []),
        "series": metadata.get("series"),
        "series_index": metadata.get("series_index"),
        "published_at": metadata.get("published_at"),
        "cover_page_index": cover_page_index,
        "page_count": len(pages),
        "cbz_path": "",
        "uploader_username": uploader_username,
    }

    upsert_work(work)
    if progress_hook is not None:
        progress_hook("write-db", "Saving work metadata", len(pages), len(pages))
    replace_work_pages(work_id, pages)
    replace_work_tags(work_id, metadata)
    _ = create_work_version_snapshot(
        work_id,
        action="ingest-cbz-editor-import",
        actor=uploader_username,
        details={"page_count": len(pages)},
    )

    if progress_hook is not None:
        progress_hook("done", "Import complete", len(pages), len(pages))

    return {
        "work_id": work_id,
        "slug": slug,
        "page_count": len(pages),
        "explicit_threshold": get_explicit_threshold(),
        "rating_before": rating_before,
        "rating_after": rating_after,
        "rating_auto_elevated": rating_after != rating_before,
    }


def ingest_editor_page(
    image_path: Path,
    metadata: dict[str, object],
    uploader_username: str,
    work_id: str | None = None,
    insert_after_page_index: int | None = None,
) -> dict[str, object]:
    ensure_storage_dirs()

    image_path = image_path.resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    moderation = moderate_image(str(image_path))
    if not moderation["allow"]:
        raise ModerationBlockedError(dict(moderation))
    auto_rating = suggested_rating_for_nsfw(moderation["nsfw_score"])

    existing_work = get_work(work_id) if work_id else None
    if work_id and not existing_work:
        raise FileNotFoundError(f"Work not found: {work_id}")

    if existing_work:
        existing_uploader = str(existing_work.get("uploader_username") or "")
        if existing_uploader and existing_uploader != uploader_username:
            raise PermissionError("Only the original uploader can append editor pages")

    resolved_work_id = work_id or uuid.uuid4().hex[:12]
    work_dir = WORKS_DIR / resolved_work_id
    pages_dir = work_dir / "pages"
    thumbs_dir = work_dir / "thumbs"
    work_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    existing_pages = list_work_page_rows(resolved_work_id)

    width: int | None = None
    height: int | None = None
    try:
        with Image.open(image_path) as image:
            width, height = image.size

            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=AVIF_QUALITY,
            )
            image_name = _store_content_addressed(pages_dir, page_bytes, "avif")

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail((360, 360))
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="WEBP",
                quality=82,
            )
            thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "webp")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert page image") from exc

    inserted_page: dict[str, object] = {
        "page_index": 0,
        "image_filename": image_name,
        "thumb_filename": thumb_name,
        "width": width,
        "height": height,
    }
    ordered_pages = list(existing_pages)
    insert_position = len(ordered_pages)
    if insert_after_page_index and ordered_pages:
        if 1 <= insert_after_page_index <= len(ordered_pages):
            insert_position = insert_after_page_index
    ordered_pages.insert(insert_position, inserted_page)

    all_pages: list[dict[str, object]] = []
    for idx, page in enumerate(ordered_pages, start=1):
        all_pages.append(
            {
                "page_index": idx,
                "image_filename": page.get("image_filename"),
                "thumb_filename": page.get("thumb_filename"),
                "width": page.get("width"),
                "height": page.get("height"),
            }
        )

    inserted_at_index = insert_position + 1

    title = str(
        metadata.get("title")
        or (existing_work.get("title") if existing_work else "")
        or image_path.stem
    )
    slug = str(
        (existing_work.get("slug") if existing_work else None)
        or metadata.get("slug")
        or slugify(title)
    )
    status = str(
        metadata.get("status")
        or (existing_work.get("status") if existing_work else "in_progress")
    )
    if status not in {"in_progress", "complete"}:
        status = "in_progress"

    cbz_path = str(
        (existing_work.get("cbz_path") if existing_work else None)
        or (CBZ_DIR / f"{resolved_work_id}.cbz")
    )
    cbz_file = Path(cbz_path)
    if not cbz_file.exists():
        with ZipFile(cbz_file, mode="w"):
            pass

    cover_page_index_raw = (
        existing_work.get("cover_page_index", 1) if existing_work else 1
    )
    if isinstance(cover_page_index_raw, int):
        cover_page_index = cover_page_index_raw
    elif isinstance(cover_page_index_raw, str) and cover_page_index_raw.isdigit():
        cover_page_index = int(cover_page_index_raw)
    else:
        cover_page_index = 1

    rating_before = _normalize_rating(
        str(
            metadata.get("rating")
            or (existing_work.get("rating") if existing_work else "Not Rated")
        )
    )
    chosen_rating = _elevate_rating(
        metadata.get("rating")
        or (existing_work.get("rating") if existing_work else "Not Rated"),
        auto_rating,
    )

    work: dict[str, object] = {
        "id": resolved_work_id,
        "slug": slug,
        "title": title,
        "summary": str(
            metadata.get("summary")
            or (existing_work.get("summary") if existing_work else "")
        ),
        "rating": chosen_rating,
        "warnings": str(
            metadata.get("warnings")
            or (
                existing_work.get("warnings")
                if existing_work
                else "No Archive Warnings Apply"
            )
        ),
        "language": str(
            metadata.get("language")
            or (existing_work.get("language") if existing_work else "en")
        ),
        "status": status,
        "creators": existing_work.get("creators", []) if existing_work else [],
        "series": metadata.get("series")
        or (existing_work.get("series_name") if existing_work else None),
        "series_index": metadata.get("series_index")
        or (existing_work.get("series_index") if existing_work else None),
        "published_at": metadata.get("published_at")
        or (existing_work.get("published_at") if existing_work else None),
        "cover_page_index": cover_page_index,
        "page_count": len(all_pages),
        "cbz_path": str(cbz_file),
        "uploader_username": str(
            existing_work.get("uploader_username") or uploader_username
        )
        if existing_work
        else uploader_username,
    }

    upsert_work(work)
    replace_work_pages(resolved_work_id, all_pages)
    if existing_work:
        _reconcile_chapters_after_page_changes(resolved_work_id)
    _ = create_work_version_snapshot(
        resolved_work_id,
        action="editor-add-page",
        actor=uploader_username,
        details={"inserted_at": inserted_at_index, "page_count": len(all_pages)},
    )

    return {
        "work_id": resolved_work_id,
        "slug": slug,
        "page_count": len(all_pages),
        "latest_page_index": inserted_at_index,
        "detected_style": str(moderation["style"]),
        "style_confidences": moderation["style_confidences"],
        "nsfw_score": float(moderation["nsfw_score"]),
        "nsfw_confidences": moderation["nsfw_confidences"],
        "explicit_threshold": get_explicit_threshold(),
        "rating_before": rating_before,
        "rating_after": chosen_rating,
        "rating_auto_elevated": chosen_rating != rating_before,
    }


def _upsert_existing_work(
    existing_work: dict[str, object], pages: list[dict[str, object]]
) -> None:
    cover_page_index = _as_int(existing_work.get("cover_page_index", 1), 1)
    work: dict[str, object] = {
        "id": str(existing_work.get("id", "")),
        "slug": str(existing_work.get("slug", "")),
        "title": str(existing_work.get("title", "Untitled")),
        "summary": str(existing_work.get("summary", "")),
        "rating": str(existing_work.get("rating", "Not Rated")),
        "warnings": str(existing_work.get("warnings", "No Archive Warnings Apply")),
        "language": str(existing_work.get("language", "en")),
        "status": str(existing_work.get("status", "in_progress")),
        "creators": existing_work.get("creators", []),
        "series": existing_work.get("series_name"),
        "series_index": existing_work.get("series_index"),
        "published_at": existing_work.get("published_at"),
        "cover_page_index": cover_page_index,
        "page_count": len(pages),
        "cbz_path": str(existing_work.get("cbz_path", "")),
        "uploader_username": existing_work.get("uploader_username"),
    }
    upsert_work(work)


def _require_editor_owner(work_id: str, uploader_username: str) -> dict[str, object]:
    existing_work = get_work(work_id)
    if not existing_work:
        raise FileNotFoundError(f"Work not found: {work_id}")

    existing_uploader = str(existing_work.get("uploader_username") or "")
    if existing_uploader and existing_uploader != uploader_username:
        raise PermissionError("Only the original uploader can manage editor pages")
    return existing_work


def _chapter_seed_members_from_range(
    page_order: list[str],
    chapter: dict[str, object],
) -> list[str]:
    start_page = _as_int(chapter.get("start_page", 1), 1)
    end_page = _as_int(chapter.get("end_page", start_page), start_page)
    start_page = max(1, min(start_page, len(page_order) or 1))
    end_page = max(start_page, min(end_page, len(page_order) or start_page))
    return page_order[start_page - 1 : end_page]


def _reconcile_chapters_after_page_changes(
    work_id: str,
    removed_image_filename: str | None = None,
) -> None:
    page_order = list_work_page_image_names(work_id)
    chapters = list_work_chapters(work_id)

    for chapter in chapters:
        chapter_id = _as_int(chapter.get("id", 0), 0)
        title = _as_str(chapter.get("title", "Untitled Chapter"), "Untitled Chapter")

        members = list_work_chapter_members(chapter_id)
        if not members:
            members = _chapter_seed_members_from_range(page_order, chapter)

        if removed_image_filename:
            members = [name for name in members if name != removed_image_filename]

        member_set = {name for name in members if name in page_order}
        ordered_members = [name for name in page_order if name in member_set]

        if not ordered_members:
            _ = delete_work_chapter(work_id, chapter_id)
            continue

        first_pos = page_order.index(ordered_members[0]) + 1
        last_pos = page_order.index(ordered_members[-1]) + 1
        _ = update_work_chapter(
            work_id,
            chapter_id=chapter_id,
            title=title,
            start_page=first_pos,
            end_page=last_pos,
        )
        replace_work_chapter_members(chapter_id, ordered_members)


def editor_replace_page_image(
    image_path: Path,
    work_id: str,
    page_index: int,
    uploader_username: str,
) -> dict[str, object]:
    image_path = image_path.resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    moderation = moderate_image(str(image_path))
    if not moderation["allow"]:
        raise ModerationBlockedError(dict(moderation))

    existing_work = _require_editor_owner(work_id, uploader_username)
    pages = list_work_page_rows(work_id)
    current_page = next(
        (p for p in pages if _as_int(p.get("page_index", 0), 0) == page_index),
        None,
    )
    if not current_page:
        raise FileNotFoundError(f"Page index not found: {page_index}")

    pages_dir = WORKS_DIR / work_id / "pages"
    thumbs_dir = WORKS_DIR / work_id / "thumbs"
    old_image_name = _as_str(current_page.get("image_filename", ""))

    width: int | None = None
    height: int | None = None
    try:
        with Image.open(image_path) as image:
            width, height = image.size
            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=AVIF_QUALITY,
            )
            image_name = _store_content_addressed(pages_dir, page_bytes, "avif")

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail((360, 360))
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="WEBP",
                quality=82,
            )
            thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "webp")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert replacement page image") from exc

    updated_pages: list[dict[str, object]] = []
    for page in pages:
        if _as_int(page.get("page_index", 0), 0) == page_index:
            updated_pages.append(
                {
                    "page_index": page_index,
                    "image_filename": image_name,
                    "thumb_filename": thumb_name,
                    "width": width,
                    "height": height,
                }
            )
        else:
            updated_pages.append(page)

    replace_work_pages(work_id, updated_pages)

    chapters = list_work_chapters(work_id)
    for chapter in chapters:
        chapter_id = _as_int(chapter.get("id", 0), 0)
        members = list_work_chapter_members(chapter_id)
        remapped_members = [
            image_name if name == old_image_name else name for name in members
        ]
        if remapped_members != members:
            replace_work_chapter_members(chapter_id, remapped_members)

    rating_before = _normalize_rating(str(existing_work.get("rating", "Not Rated")))
    rating_after = _elevate_rating(
        existing_work.get("rating", "Not Rated"),
        suggested_rating_for_nsfw(moderation["nsfw_score"]),
    )
    existing_work["rating"] = rating_after
    _reconcile_chapters_after_page_changes(work_id)
    _upsert_existing_work(existing_work, updated_pages)
    _ = create_work_version_snapshot(
        work_id,
        action="editor-replace-page",
        actor=uploader_username,
        details={"page_index": page_index},
    )
    return {
        "work_id": work_id,
        "page_count": len(updated_pages),
        "replaced_page_index": page_index,
        "explicit_threshold": get_explicit_threshold(),
        "rating_before": rating_before,
        "rating_after": rating_after,
        "rating_auto_elevated": rating_after != rating_before,
    }


def editor_delete_page(
    work_id: str, page_index: int, uploader_username: str
) -> dict[str, object]:
    existing_work = _require_editor_owner(work_id, uploader_username)
    pages = list_work_page_rows(work_id)
    current_page = next(
        (p for p in pages if _as_int(p.get("page_index", 0), 0) == page_index),
        None,
    )
    if not current_page:
        raise FileNotFoundError(f"Page index not found: {page_index}")

    image_name = _as_str(current_page.get("image_filename", ""))

    remaining = [p for p in pages if _as_int(p.get("page_index", 0), 0) != page_index]
    renumbered: list[dict[str, object]] = []
    for idx, page in enumerate(remaining, start=1):
        renumbered.append(
            {
                "page_index": idx,
                "image_filename": page.get("image_filename"),
                "thumb_filename": page.get("thumb_filename"),
                "width": page.get("width"),
                "height": page.get("height"),
            }
        )

    replace_work_pages(work_id, renumbered)
    _reconcile_chapters_after_page_changes(work_id, removed_image_filename=image_name)
    _upsert_existing_work(existing_work, renumbered)
    _ = create_work_version_snapshot(
        work_id,
        action="editor-delete-page",
        actor=uploader_username,
        details={"deleted_page_index": page_index},
    )
    return {
        "work_id": work_id,
        "page_count": len(renumbered),
        "deleted_page_index": page_index,
    }


def editor_move_page(
    work_id: str,
    from_index: int,
    to_index: int,
    uploader_username: str,
) -> dict[str, object]:
    existing_work = _require_editor_owner(work_id, uploader_username)
    pages = list_work_page_rows(work_id)
    if (
        from_index < 1
        or from_index > len(pages)
        or to_index < 1
        or to_index > len(pages)
    ):
        raise ValueError("Page index out of range")

    source = pages.pop(from_index - 1)
    pages.insert(to_index - 1, source)

    reordered: list[dict[str, object]] = []
    for idx, page in enumerate(pages, start=1):
        reordered.append(
            {
                "page_index": idx,
                "image_filename": page.get("image_filename"),
                "thumb_filename": page.get("thumb_filename"),
                "width": page.get("width"),
                "height": page.get("height"),
            }
        )

    replace_work_pages(work_id, reordered)
    _reconcile_chapters_after_page_changes(work_id)
    _upsert_existing_work(existing_work, reordered)
    _ = create_work_version_snapshot(
        work_id,
        action="editor-move-page",
        actor=uploader_username,
        details={"from": from_index, "to": to_index},
    )
    return {
        "work_id": work_id,
        "page_count": len(reordered),
        "from": from_index,
        "to": to_index,
    }


def editor_reorder_gallery(
    work_id: str,
    ordered_filenames: list[str],
    chapter_members: dict[str, list[str]],
    uploader_username: str,
) -> dict[str, object]:
    existing_work = _require_editor_owner(work_id, uploader_username)
    pages = list_work_page_rows(work_id)
    if not pages:
        raise ValueError("No pages found")

    by_filename: dict[str, dict[str, object]] = {}
    for page in pages:
        name = _as_str(page.get("image_filename", ""))
        if name:
            by_filename[name] = page

    unique_order: list[str] = []
    seen: set[str] = set()
    for name in ordered_filenames:
        if name in by_filename and name not in seen:
            unique_order.append(name)
            seen.add(name)

    if len(unique_order) != len(by_filename):
        raise ValueError("Ordered page list does not match existing pages")

    reordered: list[dict[str, object]] = []
    for idx, name in enumerate(unique_order, start=1):
        page = by_filename[name]
        reordered.append(
            {
                "page_index": idx,
                "image_filename": page.get("image_filename"),
                "thumb_filename": page.get("thumb_filename"),
                "width": page.get("width"),
                "height": page.get("height"),
            }
        )

    replace_work_pages(work_id, reordered)

    page_order = list_work_page_image_names(work_id)
    page_set = set(page_order)
    chapters = list_work_chapters(work_id)

    for chapter in chapters:
        chapter_id = _as_int(chapter.get("id", 0), 0)
        title = _as_str(chapter.get("title", "Untitled Chapter"))
        requested = chapter_members.get(str(chapter_id))

        if requested is None:
            members = list_work_chapter_members(chapter_id)
            if not members:
                members = _chapter_seed_members_from_range(page_order, chapter)
        else:
            members = [name for name in requested if name in page_set]

        member_set = set(members)
        ordered_members = [name for name in page_order if name in member_set]

        if not ordered_members:
            _ = delete_work_chapter(work_id, chapter_id)
            continue

        start_page = page_order.index(ordered_members[0]) + 1
        end_page = page_order.index(ordered_members[-1]) + 1
        _ = update_work_chapter(
            work_id,
            chapter_id=chapter_id,
            title=title,
            start_page=start_page,
            end_page=end_page,
        )
        replace_work_chapter_members(chapter_id, ordered_members)

    _upsert_existing_work(existing_work, reordered)
    _ = create_work_version_snapshot(
        work_id,
        action="editor-reorder-gallery",
        actor=uploader_username,
        details={"page_count": len(reordered)},
    )
    return {
        "work_id": work_id,
        "page_count": len(reordered),
    }


def editor_add_chapter(
    work_id: str,
    title: str,
    start_page: int,
    end_page: int,
    uploader_username: str,
) -> dict[str, object]:
    _ = _require_editor_owner(work_id, uploader_username)
    page_count = len(list_work_page_rows(work_id))
    if start_page < 1 or end_page < start_page or end_page > page_count:
        raise ValueError("Chapter range is invalid")
    result = add_work_chapter(
        work_id, title=title, start_page=start_page, end_page=end_page
    )
    _ = create_work_version_snapshot(
        work_id,
        action="editor-add-chapter",
        actor=uploader_username,
        details={
            "chapter_title": title,
            "start_page": start_page,
            "end_page": end_page,
        },
    )
    return result


def editor_update_chapter(
    work_id: str,
    chapter_id: int,
    title: str,
    start_page: int,
    end_page: int,
    uploader_username: str,
) -> bool:
    _ = _require_editor_owner(work_id, uploader_username)
    page_count = len(list_work_page_rows(work_id))
    if start_page < 1 or end_page < start_page or end_page > page_count:
        raise ValueError("Chapter range is invalid")
    updated = update_work_chapter(
        work_id,
        chapter_id=chapter_id,
        title=title,
        start_page=start_page,
        end_page=end_page,
    )
    if not updated:
        return False

    page_order = list_work_page_image_names(work_id)
    selected = page_order[start_page - 1 : end_page]
    replace_work_chapter_members(chapter_id, selected)
    _ = create_work_version_snapshot(
        work_id,
        action="editor-update-chapter",
        actor=uploader_username,
        details={
            "chapter_id": chapter_id,
            "start_page": start_page,
            "end_page": end_page,
        },
    )
    return True


def editor_delete_chapter(
    work_id: str, chapter_id: int, uploader_username: str
) -> bool:
    _ = _require_editor_owner(work_id, uploader_username)
    deleted = delete_work_chapter(work_id, chapter_id)
    if deleted:
        _ = create_work_version_snapshot(
            work_id,
            action="editor-delete-chapter",
            actor=uploader_username,
            details={"chapter_id": chapter_id},
        )
    return deleted
