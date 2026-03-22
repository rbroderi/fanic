from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from typing import cast
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pillow_avif  # noqa: F401 Register AVIF support with Pillow  # pyright: ignore[reportUnusedImport]
from PIL import Image
from PIL import UnidentifiedImageError
from tqdm import tqdm

from fanic.db import get_connection
from fanic.moderation import get_explicit_threshold
from fanic.moderation import moderate_image
from fanic.moderation import moderate_image_bytes
from fanic.moderation import suggested_rating_for_nsfw
from fanic.repository import WorkChapterRow
from fanic.repository import WorkPageRow
from fanic.repository import add_work_chapter
from fanic.repository import count_uploaded_pages_for_user
from fanic.repository import create_work_version_snapshot
from fanic.repository import delete_work_chapter
from fanic.repository import get_work
from fanic.repository import list_work_chapter_members
from fanic.repository import list_work_chapters
from fanic.repository import list_work_page_image_names
from fanic.repository import list_work_page_rows
from fanic.repository import replace_work_chapter_members
from fanic.repository import replace_work_pages
from fanic.repository import replace_work_tags
from fanic.repository import update_work_chapter
from fanic.repository import upsert_work
from fanic.settings import CBZ_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings
from fanic.utils import slugify

Image.init()
SUPPORTED_IMAGE_EXTENSIONS = {
    extension.lower()
    for extension, format_name in Image.registered_extensions().items()
    if format_name in Image.OPEN
}
_SETTINGS = get_settings()
IMAGE_AVIF_QUALITY = _SETTINGS.image_avif_quality
THUMBNAIL_AVIF_QUALITY = _SETTINGS.thumbnail_avif_quality
MAX_INGEST_PAGES = int(getattr(_SETTINGS, "max_ingest_pages", 2000))
MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES = int(
    getattr(_SETTINGS, "max_cbz_member_uncompressed_bytes", 134217728)
)
MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES = int(
    getattr(_SETTINGS, "max_cbz_total_uncompressed_bytes", 2147483648)
)
MAX_UPLOAD_IMAGE_PIXELS = int(getattr(_SETTINGS, "max_upload_image_pixels", 40000000))
USER_PAGE_SOFT_CAP = int(getattr(_SETTINGS, "user_page_soft_cap", 2000))
USER_PAGE_QUALITY_RAMP_MULTIPLIER = float(
    getattr(_SETTINGS, "user_page_quality_ramp_multiplier", 1.5)
)

type ComicInfoValue = str | list[str]
type ComicInfoMetadata = dict[str, ComicInfoValue]


_NATURAL_SORT_RE = re.compile(r"(\d+)")


def _natural_member_sort_key(member: str) -> tuple[object, ...]:
    base_name = Path(member).name
    parts = _NATURAL_SORT_RE.split(base_name.lower())
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part)
    return tuple(key)


def _cbz_member_directory(member: str) -> str:
    parent = PurePosixPath(member).parent.as_posix()
    return "" if parent == "." else parent


def _chapter_title_from_cbz_directory(directory: str) -> str:
    title = directory.strip().strip("/")
    return title if title else "Untitled Chapter"


def _group_cbz_pages_by_directory(
    image_members: Sequence[str],
    pages: Sequence[WorkPageRow],
) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {}
    for member, page in zip(image_members, pages):
        directory = _cbz_member_directory(member)
        if not directory:
            continue
        image_filename = _as_str(page.get("image_filename", ""), "")
        if not image_filename:
            continue
        current = grouped.get(directory)
        if current is None:
            grouped[directory] = [image_filename]
        else:
            current.append(image_filename)
    return [(directory, members) for directory, members in grouped.items() if members]


def _replace_work_chapters_from_cbz_directories(
    work_id: str,
    image_members: Sequence[str],
    pages: Sequence[WorkPageRow],
) -> int:
    existing_chapters = list_work_chapters(work_id)
    for chapter in existing_chapters:
        chapter_id = _as_int(chapter.get("id", 0), 0)
        if chapter_id > 0:
            _ = delete_work_chapter(work_id, chapter_id)

    grouped_members = _group_cbz_pages_by_directory(image_members, pages)
    if not grouped_members:
        return 0

    page_positions: dict[str, int] = {}
    for page in pages:
        image_filename = _as_str(page.get("image_filename", ""), "")
        if not image_filename:
            continue
        page_positions[image_filename] = _as_int(page.get("page_index", 0), 0)

    created = 0
    for directory, members in grouped_members:
        valid_members = [name for name in members if name in page_positions]
        if not valid_members:
            continue
        positions = [page_positions[name] for name in valid_members]
        start_page = min(positions)
        end_page = max(positions)
        chapter_title = _chapter_title_from_cbz_directory(directory)
        chapter = add_work_chapter(
            work_id,
            title=chapter_title,
            start_page=start_page,
            end_page=end_page,
        )
        chapter_id = _as_int(chapter.get("id", 0), 0)
        if chapter_id < 1:
            continue
        replace_work_chapter_members(chapter_id, valid_members)
        created += 1

    return created


def _render_image_bytes(image: Image.Image, *, fmt: str, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=quality)
    return buffer.getvalue()


def _content_addressed_rel_path(data: bytes, extension: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    stripped_ext = extension.strip().lower().lstrip(".")
    normalized_ext = stripped_ext if stripped_ext else "bin"
    return f"_objects/{digest[:2]}/{digest}.{normalized_ext}"


def _store_content_addressed(base_dir: Path, data: bytes, extension: str) -> str:
    _assert_safe_storage_dir(base_dir)
    rel_path = _content_addressed_rel_path(data, extension)
    target = base_dir / rel_path
    _assert_safe_storage_target(base_dir, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _assert_path_not_symlink(target.parent)
    if target.exists():
        target_stat = target.stat()
        if target_stat.st_nlink > 1:
            raise ValueError(f"Unsafe linked upload target detected: {target}")
        return rel_path

    try:
        with target.open("xb") as handle:
            handle.write(data)
        target_stat = target.stat()
        if target_stat.st_nlink > 1:
            target.unlink(missing_ok=True)
            raise ValueError(f"Unsafe linked upload target detected: {target}")
    except FileExistsError:
        # Another request wrote the same hash concurrently.
        pass
    return rel_path


def _assert_path_not_symlink(path: Path) -> None:
    candidate = path
    while True:
        if candidate.exists() and candidate.is_symlink():
            raise ValueError(f"Refusing upload path through symlink: {candidate}")
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent


def _assert_safe_storage_dir(base_dir: Path) -> None:
    resolved_base = base_dir.resolve()
    resolved_works = WORKS_DIR.resolve()
    try:
        _ = resolved_base.relative_to(resolved_works)
    except ValueError as exc:
        raise ValueError(
            f"Upload base directory escapes storage root: {base_dir}"
        ) from exc
    _assert_path_not_symlink(resolved_base)


def _assert_safe_storage_target(base_dir: Path, target: Path) -> None:
    resolved_base = base_dir.resolve()
    resolved_target_parent = target.parent.resolve()
    try:
        _ = resolved_target_parent.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Upload target escapes storage root: {target}") from exc


def _safe_work_dirs(work_id: str) -> tuple[Path, Path, Path]:
    work_dir = WORKS_DIR / work_id
    pages_dir = work_dir / "pages"
    thumbs_dir = work_dir / "thumbs"

    for candidate in (work_dir, pages_dir, thumbs_dir):
        _assert_safe_storage_dir(candidate)

    work_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    return work_dir, pages_dir, thumbs_dir


def _quality_for_account_page(account_page_number: int) -> int:
    base_quality = int(IMAGE_AVIF_QUALITY)
    if account_page_number <= USER_PAGE_SOFT_CAP:
        return max(1, base_quality)

    ramp_limit = int(round(USER_PAGE_SOFT_CAP * USER_PAGE_QUALITY_RAMP_MULTIPLIER))
    if ramp_limit <= USER_PAGE_SOFT_CAP:
        return 1
    if account_page_number >= ramp_limit:
        return 1

    ramp_progress = (account_page_number - USER_PAGE_SOFT_CAP) / (
        ramp_limit - USER_PAGE_SOFT_CAP
    )
    quality_value = round(base_quality - (base_quality - 1) * ramp_progress)
    return max(1, int(quality_value))


def _validate_zip_archive_limits(zip_file: ZipFile) -> None:
    infos = [info for info in zip_file.infolist() if not info.is_dir()]
    total_uncompressed = 0
    for info in infos:
        file_size = int(info.file_size)
        total_uncompressed += file_size
        if file_size > MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES:
            raise ValueError(
                "CBZ member exceeds maximum allowed uncompressed size "
                f"({file_size} > {MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES}): {info.filename}"
            )
    if total_uncompressed > MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES:
        raise ValueError(
            "CBZ exceeds maximum allowed total uncompressed size "
            f"({total_uncompressed} > {MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES})"
        )


def _assert_image_pixels_within_limit(image: Image.Image, context: str) -> None:
    width, height = image.size
    total_pixels = int(width) * int(height)
    if total_pixels > MAX_UPLOAD_IMAGE_PIXELS:
        raise ValueError(
            f"{context} exceeds maximum allowed pixel count "
            f"({total_pixels} > {MAX_UPLOAD_IMAGE_PIXELS})"
        )


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
    normalized_current = _normalize_rating(str(current if current else "Not Rated"))
    normalized_suggested = _normalize_rating(str(suggested if suggested else ""))
    if normalized_suggested == "Explicit" and normalized_current != "Explicit":
        return "Explicit"
    return normalized_current


def _clean_xml_value(value: str | None) -> str:
    return (value if value else "").strip()


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
    return suffix in SUPPORTED_IMAGE_EXTENSIONS


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
        _validate_zip_archive_limits(zip_file)
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

        title = str(metadata.get("title") if metadata.get("title") else cbz_path.stem)
        work_id = str(
            metadata.get("id") if metadata.get("id") else uuid.uuid4().hex[:12]
        )
        slug = str(metadata.get("slug") if metadata.get("slug") else slugify(title))

        _, pages_dir, thumbs_dir = _safe_work_dirs(work_id)

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
                f"{', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
            )

        if len(image_members) > MAX_INGEST_PAGES:
            raise ValueError(
                "CBZ exceeds maximum allowed page count "
                f"({len(image_members)} > {MAX_INGEST_PAGES})"
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
                    else 999999,
                    _natural_member_sort_key(name),
                ),
            )
        else:
            image_members = sorted(image_members, key=_natural_member_sort_key)

        if progress_hook is not None:
            progress_hook(
                "prepare-pages",
                "Preparing pages",
                0,
                len(image_members),
            )

        pages: list[WorkPageRow] = []
        uploader_pages_before = count_uploaded_pages_for_user(uploader_username)
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
                        _assert_image_pixels_within_limit(image, "Uploaded CBZ page")
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
                        account_page_number = uploader_pages_before + index
                        effective_quality = _quality_for_account_page(
                            account_page_number
                        )
                        page_bytes = _render_image_bytes(
                            page_image,
                            fmt="AVIF",
                            quality=effective_quality,
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
                            fmt="AVIF",
                            quality=THUMBNAIL_AVIF_QUALITY,
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
                            "avif",
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
    imported_chapter_count = _replace_work_chapters_from_cbz_directories(
        work_id,
        image_members,
        pages,
    )
    replace_work_tags(work_id, metadata)
    _ = create_work_version_snapshot(
        work_id,
        action="ingest-cbz-editor-import",
        actor=uploader_username,
        details={
            "page_count": len(pages),
            "chapter_count": imported_chapter_count,
        },
    )

    if progress_hook is not None:
        progress_hook("done", "Import complete", len(pages), len(pages))

    return {
        "work_id": work_id,
        "slug": slug,
        "page_count": len(pages),
        "chapter_count": imported_chapter_count,
        "detected_explicit_confidence": max_nsfw_score,
        "explicit_threshold": get_explicit_threshold(),
        "rating_before": rating_before,
        "rating_after": rating_after,
        "rating_auto_elevated": rating_after != rating_before,
    }


def convert_existing_thumbs_to_avif(*, dry_run: bool = False) -> dict[str, object]:
    ensure_storage_dirs()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT work_id, page_index, image_filename, thumb_filename
            FROM pages
            ORDER BY work_id, page_index
            """
        ).fetchall()

    scanned = 0
    converted = 0
    already_avif = 0
    missing_source = 0
    failed = 0
    updates: list[tuple[str, str, int]] = []

    for row in rows:
        scanned += 1

        work_id = str(row["work_id"])
        page_index = int(row["page_index"])
        image_filename = str(row["image_filename"] if row["image_filename"] else "")
        thumb_filename = str(row["thumb_filename"] if row["thumb_filename"] else "")

        thumbs_dir = WORKS_DIR / work_id / "thumbs"
        pages_dir = WORKS_DIR / work_id / "pages"
        thumb_path = thumbs_dir / thumb_filename if thumb_filename else None
        image_path = pages_dir / image_filename

        source_path: Path | None = None
        if image_path.exists():
            source_path = image_path
        elif thumb_path is not None and thumb_path.exists():
            source_path = thumb_path

        if source_path is None:
            missing_source += 1
            continue

        try:
            with Image.open(source_path) as image:
                thumb_image = _prepare_image_for_avif(image)
                thumb_image.thumbnail((360, 360))
                thumb_bytes = _render_image_bytes(
                    thumb_image,
                    fmt="AVIF",
                    quality=THUMBNAIL_AVIF_QUALITY,
                )
        except (UnidentifiedImageError, OSError, ValueError):
            failed += 1
            continue

        if dry_run:
            new_thumb_name = _content_addressed_rel_path(thumb_bytes, "avif")
        else:
            new_thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "avif")

        if new_thumb_name == thumb_filename:
            already_avif += 1
            continue

        converted += 1
        updates.append((new_thumb_name, work_id, page_index))

    if not dry_run and updates:
        with get_connection() as connection:
            connection.executemany(
                """
                UPDATE pages
                SET thumb_filename = ?
                WHERE work_id = ? AND page_index = ?
                """,
                updates,
            )

    return {
        "scanned": scanned,
        "converted": converted,
        "already_avif": already_avif,
        "missing_source": missing_source,
        "failed": failed,
        "updated_rows": 0 if dry_run else len(updates),
        "dry_run": dry_run,
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
        existing_uploader = str(
            existing_work.get("uploader_username")
            if existing_work.get("uploader_username")
            else ""
        )
        if existing_uploader and existing_uploader != uploader_username:
            raise PermissionError("Only the original uploader can append editor pages")

    resolved_work_id = work_id if work_id else uuid.uuid4().hex[:12]
    _, pages_dir, thumbs_dir = _safe_work_dirs(resolved_work_id)

    existing_pages = list_work_page_rows(resolved_work_id)

    width: int | None = None
    height: int | None = None
    try:
        uploader_pages_before = count_uploaded_pages_for_user(uploader_username)
        account_page_number = uploader_pages_before + 1
        effective_quality = _quality_for_account_page(account_page_number)
        with Image.open(image_path) as image:
            _assert_image_pixels_within_limit(image, "Uploaded editor page")
            width, height = image.size

            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=effective_quality,
            )
            image_name = _store_content_addressed(pages_dir, page_bytes, "avif")

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail((360, 360))
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="AVIF",
                quality=THUMBNAIL_AVIF_QUALITY,
            )
            thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "avif")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert page image") from exc

    inserted_page: WorkPageRow = {
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

    all_pages: list[WorkPageRow] = []
    for idx, page in enumerate(ordered_pages, start=1):
        all_pages.append(
            {
                "page_index": idx,
                "image_filename": page["image_filename"],
                "thumb_filename": page["thumb_filename"],
                "width": page["width"],
                "height": page["height"],
            }
        )

    inserted_at_index = insert_position + 1

    title = str(
        metadata.get("title")
        if metadata.get("title")
        else (
            existing_work.get("title")
            if existing_work and existing_work.get("title")
            else image_path.stem
        )
    )
    slug = str(
        (existing_work.get("slug") if existing_work else None)
        if (existing_work and existing_work.get("slug"))
        else (metadata.get("slug") if metadata.get("slug") else slugify(title))
    )
    status = str(
        metadata.get("status")
        if metadata.get("status")
        else (existing_work.get("status") if existing_work else "in_progress")
    )
    if status not in {"in_progress", "complete"}:
        status = "in_progress"

    cbz_path = str(
        (existing_work.get("cbz_path") if existing_work else None)
        if (existing_work and existing_work.get("cbz_path"))
        else (CBZ_DIR / f"{resolved_work_id}.cbz")
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
            if metadata.get("rating")
            else (existing_work.get("rating") if existing_work else "Not Rated")
        )
    )
    chosen_rating = _elevate_rating(
        metadata.get("rating")
        if metadata.get("rating")
        else (existing_work.get("rating") if existing_work else "Not Rated"),
        auto_rating,
    )

    work: dict[str, object] = {
        "id": resolved_work_id,
        "slug": slug,
        "title": title,
        "summary": str(
            metadata.get("summary")
            if metadata.get("summary")
            else (existing_work.get("summary") if existing_work else "")
        ),
        "rating": chosen_rating,
        "warnings": str(
            metadata.get("warnings")
            if metadata.get("warnings")
            else (
                existing_work.get("warnings")
                if existing_work
                else "No Archive Warnings Apply"
            )
        ),
        "language": str(
            metadata.get("language")
            if metadata.get("language")
            else (existing_work.get("language") if existing_work else "en")
        ),
        "status": status,
        "creators": existing_work.get("creators", []) if existing_work else [],
        "series": metadata.get("series")
        if metadata.get("series")
        else (existing_work.get("series_name") if existing_work else None),
        "series_index": metadata.get("series_index")
        if metadata.get("series_index")
        else (existing_work.get("series_index") if existing_work else None),
        "published_at": metadata.get("published_at")
        if metadata.get("published_at")
        else (existing_work.get("published_at") if existing_work else None),
        "cover_page_index": cover_page_index,
        "page_count": len(all_pages),
        "cbz_path": str(cbz_file),
        "uploader_username": str(
            existing_work.get("uploader_username")
            if existing_work.get("uploader_username")
            else uploader_username
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
    existing_work: dict[str, object], pages: list[WorkPageRow]
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

    existing_uploader = str(
        existing_work.get("uploader_username")
        if existing_work.get("uploader_username")
        else ""
    )
    if existing_uploader and existing_uploader != uploader_username:
        raise PermissionError("Only the original uploader can manage editor pages")
    return existing_work


def _chapter_seed_members_from_range(
    page_order: list[str],
    chapter: WorkChapterRow,
) -> list[str]:
    start_page = chapter["start_page"]
    end_page = chapter["end_page"]
    page_order_len_or_one = len(page_order) if len(page_order) else 1
    start_page = max(1, min(start_page, page_order_len_or_one))
    end_page = max(
        start_page, min(end_page, len(page_order) if len(page_order) else start_page)
    )
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
        (p for p in pages if p["page_index"] == page_index),
        None,
    )
    if not current_page:
        raise FileNotFoundError(f"Page index not found: {page_index}")

    pages_dir = WORKS_DIR / work_id / "pages"
    thumbs_dir = WORKS_DIR / work_id / "thumbs"
    _assert_safe_storage_dir(pages_dir)
    _assert_safe_storage_dir(thumbs_dir)
    old_image_name = _as_str(current_page["image_filename"], "")

    width: int | None = None
    height: int | None = None
    try:
        uploader_pages_before = count_uploaded_pages_for_user(uploader_username)
        effective_quality = _quality_for_account_page(uploader_pages_before)
        with Image.open(image_path) as image:
            _assert_image_pixels_within_limit(image, "Replacement editor page")
            width, height = image.size
            page_image = _prepare_image_for_avif(image)
            page_bytes = _render_image_bytes(
                page_image,
                fmt="AVIF",
                quality=effective_quality,
            )
            image_name = _store_content_addressed(pages_dir, page_bytes, "avif")

            thumb_image = _prepare_image_for_avif(image)
            thumb_image.thumbnail((360, 360))
            thumb_bytes = _render_image_bytes(
                thumb_image,
                fmt="AVIF",
                quality=THUMBNAIL_AVIF_QUALITY,
            )
            thumb_name = _store_content_addressed(thumbs_dir, thumb_bytes, "avif")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Failed to convert replacement page image") from exc

    updated_pages: list[WorkPageRow] = []
    for page in pages:
        if page["page_index"] == page_index:
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
        (p for p in pages if p["page_index"] == page_index),
        None,
    )
    if not current_page:
        raise FileNotFoundError(f"Page index not found: {page_index}")

    image_name = _as_str(current_page["image_filename"], "")

    remaining = [p for p in pages if p["page_index"] != page_index]
    renumbered: list[WorkPageRow] = []
    for idx, page in enumerate(remaining, start=1):
        renumbered.append(
            {
                "page_index": idx,
                "image_filename": page["image_filename"],
                "thumb_filename": page["thumb_filename"],
                "width": page["width"],
                "height": page["height"],
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

    reordered: list[WorkPageRow] = []
    for idx, page in enumerate(pages, start=1):
        reordered.append(
            {
                "page_index": idx,
                "image_filename": page["image_filename"],
                "thumb_filename": page["thumb_filename"],
                "width": page["width"],
                "height": page["height"],
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

    by_filename: dict[str, WorkPageRow] = {}
    for page in pages:
        name = _as_str(page["image_filename"], "")
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

    reordered: list[WorkPageRow] = []
    for idx, name in enumerate(unique_order, start=1):
        page = by_filename[name]
        reordered.append(
            {
                "page_index": idx,
                "image_filename": page["image_filename"],
                "thumb_filename": page["thumb_filename"],
                "width": page["width"],
                "height": page["height"],
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
