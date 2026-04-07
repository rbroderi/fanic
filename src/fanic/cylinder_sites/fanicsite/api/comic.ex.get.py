import json
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import cast
from urllib.parse import quote
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

from defusedxml import ElementTree as ET
from pathvalidate import sanitize_filename

from fanic.cylinder_sites.common.logging_utils import log_exception
from fanic.cylinder_sites.common.logging_utils import request_id
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import json_response
from fanic.cylinder_sites.common.responses import media_url
from fanic.cylinder_sites.common.responses import page_file_for
from fanic.cylinder_sites.common.responses import redirect_see_other
from fanic.cylinder_sites.common.responses import send_file
from fanic.cylinder_sites.common.responses import stable_api_error
from fanic.cylinder_sites.common.responses import thumb_file_for
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.session import current_user
from fanic.media import MediaService
from fanic.media import build_media_service
from fanic.repository.works import can_view_work
from fanic.repository.works import get_manifest
from fanic.repository.works import get_page_files
from fanic.repository.works import get_work
from fanic.repository.works import get_work_version_manifest
from fanic.repository.works import list_work_chapter_members
from fanic.repository.works import list_work_chapters
from fanic.repository.works import list_work_page_rows
from fanic.repository.works import list_work_versions
from fanic.repository.works import list_works
from fanic.repository.works import load_progress
from fanic.repository.works import set_work_cbz_path
from fanic.settings import CBZ_DIR
from fanic.settings import get_settings
from fanic.utils import slugify

ET_ANY = cast(Any, ET)
_MEDIA_SERVICE: MediaService = build_media_service(get_settings())


def _can_view_work(request: RequestLike, work: Mapping[str, object]) -> bool:
    return can_view_work(current_user(request), work)


def _csv_join(values: list[str]) -> str:
    return ", ".join(value for value in values if value.strip())


def _split_csv_field(value: object) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in cast(list[object], value):
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    text_value = str(value if value else "").strip()
    if not text_value:
        return []
    return [part.strip() for part in text_value.split(",") if part.strip()]


def _split_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            return int(stripped)
    return default


def _map_fanic_rating_to_comicinfo_age_rating(value: str) -> str:
    normalized = value.strip().lower()
    age_rating_map: dict[str, str] = {
        "general audiences": "Everyone",
        "teen and up audiences": "Teen",
        "mature": "Mature 17+",
        "explicit": "Adults Only 18+",
        "not rated": "Unknown",
    }
    return age_rating_map.get(normalized, "Unknown")


def _fanic_scaninformation(work: Mapping[str, object]) -> str:
    fanic_meta: dict[str, object] = {}

    work_id = str(work.get("id", "") if work.get("id", "") else "").strip()
    if work_id:
        fanic_meta["id"] = work_id

    slug = str(work.get("slug", "") if work.get("slug", "") else "").strip()
    if slug:
        fanic_meta["slug"] = slug

    status = str(work.get("status", "") if work.get("status", "") else "").strip()
    if status:
        fanic_meta["status"] = status

    cover_page_index = _split_int(work.get("cover_page_index", 0), 0)
    if cover_page_index > 0:
        fanic_meta["cover_page_index"] = cover_page_index

    creators = _split_csv_field(work.get("creators", []))
    if creators:
        fanic_meta["creators"] = creators

    if not fanic_meta:
        return ""
    return f"fanic_meta={json.dumps(fanic_meta, ensure_ascii=True)}"


def _extract_tag_names(work: Mapping[str, object], tag_type: str) -> list[str]:
    tags_obj = work.get("tags")
    if not isinstance(tags_obj, list):
        return []
    names: list[str] = []
    for tag in cast(list[object], tags_obj):
        if not isinstance(tag, dict):
            continue
        tag_map = cast(dict[str, object], tag)
        if str(tag_map.get("type", "")) != tag_type:
            continue
        name = str(tag_map.get("name", "")).strip()
        if name:
            names.append(name)
    return names


def _build_comicinfo_xml(
    work: Mapping[str, object],
    pages: Sequence[Mapping[str, object]],
) -> str:
    root = ET_ANY.Element("ComicInfo")

    def add_text_element(name: str, value: str) -> None:
        ET_ANY.SubElement(root, name).text = value

    # Preserve schema sequence order from ComicInfo v2.0 for strict validator compatibility.
    title = str(work.get("title", "Untitled"))
    add_text_element("Title", title)

    series_name = str(work.get("series_name", "") if work.get("series_name", "") else "").strip()
    if series_name:
        add_text_element("Series", series_name)

    series_index = str(work.get("series_index", "") if work.get("series_index", "") else "").strip()
    if series_index:
        add_text_element("Number", series_index)

    page_count_int = _split_int(work.get("page_count", 0), 0)
    add_text_element("Count", str(page_count_int))

    add_text_element("Summary", str(work.get("summary", "")))

    freeform_names = _extract_tag_names(work, "freeform")
    warning_names = _extract_tag_names(work, "archive_warning")
    notes_payload: list[str] = []
    if freeform_names:
        notes_payload.append(f"freeform_tags={_csv_join(freeform_names)}")
    if warning_names:
        notes_payload.append(f"warnings={_csv_join(warning_names)}")
    if notes_payload:
        add_text_element("Notes", "; ".join(notes_payload))

    published_at = str(work.get("published_at", "") if work.get("published_at", "") else "").strip()
    if published_at:
        parts = published_at.split("-")
        if len(parts) == 3:
            year, month, day = parts
            if year:
                add_text_element("Year", year)
                add_text_element("Month", month if month else "01")
                add_text_element("Day", day if day else "01")

    creators = _split_csv_field(work.get("creators", []))
    if creators:
        add_text_element("Writer", _csv_join(creators))

    category_names = _extract_tag_names(work, "category")
    if category_names:
        add_text_element("Genre", _csv_join(category_names))

    add_text_element("PageCount", str(page_count_int))
    add_text_element("LanguageISO", str(work.get("language", "en")))

    character_names = _extract_tag_names(work, "character")
    if character_names:
        add_text_element("Characters", _csv_join(character_names))

    scan_information = _fanic_scaninformation(work)
    if scan_information:
        add_text_element("ScanInformation", scan_information)

    relationship_names = _extract_tag_names(work, "relationship")
    if relationship_names:
        add_text_element("StoryArc", _csv_join(relationship_names))

    fandom_names = _extract_tag_names(work, "fandom")
    if fandom_names:
        add_text_element("SeriesGroup", _csv_join(fandom_names))

    age_rating = _map_fanic_rating_to_comicinfo_age_rating(str(work.get("rating", "Not Rated")))
    add_text_element("AgeRating", age_rating)

    cover_page_index = _split_int(work.get("cover_page_index", 1), 1)
    pages_element = ET_ANY.SubElement(root, "Pages")
    for page in pages:
        page_index = _split_int(page.get("page_index", 1), 1)
        image_index = max(0, page_index - 1)
        page_attrs: dict[str, str] = {"Image": str(image_index)}

        page_type = "FrontCover" if page_index == cover_page_index else "Story"
        page_attrs["Type"] = page_type

        width = _split_int(page.get("width", -1), -1)
        height = _split_int(page.get("height", -1), -1)
        if width > 0:
            page_attrs["ImageWidth"] = str(width)
        if height > 0:
            page_attrs["ImageHeight"] = str(height)

        ET_ANY.SubElement(pages_element, "Page", attrib=page_attrs)

    main_character = character_names[0] if character_names else ""
    if main_character:
        add_text_element("MainCharacterOrTeam", main_character)

    if warning_names:
        add_text_element("Review", _csv_join(warning_names))

    xml_bytes = ET_ANY.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def _chapter_members_with_fallback(
    chapter: Mapping[str, object],
    page_order: list[str],
) -> list[str]:
    chapter_id = _split_int(chapter.get("id", 0), 0)
    members = list_work_chapter_members(chapter_id)
    if members:
        return [name for name in members if name in page_order]

    start_page = _split_int(chapter.get("start_page", 1), 1)
    end_page = _split_int(chapter.get("end_page", start_page), start_page)
    start_page = max(1, min(start_page, len(page_order) if len(page_order) else 1))
    end_page = max(
        start_page,
        min(end_page, len(page_order) if len(page_order) else start_page),
    )
    return page_order[start_page - 1 : end_page]


def _safe_filename(name: str, fallback: str) -> str:
    safe = sanitize_filename(name, replacement_text="_").strip(" .")
    return safe if safe else fallback


def _chapter_folder_name(chapter_index: int, title: str) -> str:
    base_slug = slugify(title)
    base = base_slug if base_slug else "chapter"
    return _safe_filename(f"chapter-{chapter_index:03d}-{base}", "chapter")


def _current_export_key(work_id: str, work: Mapping[str, object]) -> str:
    versions = list_work_versions(work_id, limit=1)
    if versions:
        return f"version:{str(versions[0].get('version_id', ''))}"
    updated_at = str(work.get("updated_at", ""))
    page_count = _split_int(work.get("page_count", 0), 0)
    return f"legacy:{updated_at}:{page_count}"


def _export_key_filename_token(export_key: str) -> str:
    token = "".join(character.lower() if character.isalnum() else "-" for character in export_key.strip()).strip("-")
    return token if token else "v0"


def _cache_meta_path(archive_path: Path) -> Path:
    return archive_path.with_suffix(f"{archive_path.suffix}.meta.json")


def _read_cache_meta(cache_path: Path) -> dict[str, object] | None:
    if not cache_path.exists():
        return None
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return cast(dict[str, object], raw)


def _write_cache_meta(cache_path: Path, payload: dict[str, object]) -> None:
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _resolve_archive_path(
    work_id: str,
    work: Mapping[str, object],
    export_key: str,
) -> Path:
    token = _export_key_filename_token(export_key)
    cbz_path = str(work.get("cbz_path", "") if work.get("cbz_path", "") else "").strip()
    if cbz_path and "://" not in cbz_path:
        candidate = Path(cbz_path)
        if candidate.suffix.lower() == ".cbz" and token in candidate.stem.lower():
            return candidate
    return CBZ_DIR / f"{work_id}.{token}.cbz"


def _download_archive_filename(
    work_id: str,
    work: Mapping[str, object],
    export_key: str,
) -> str:
    slug = work.get("slug")
    base_name = str(slug).strip() if isinstance(slug, str) and slug.strip() else work_id
    token = _export_key_filename_token(export_key)
    requested_name = f"{base_name}.{token}.cbz"
    return _safe_filename(requested_name, f"{work_id}.{token}.cbz")


def _archive_media_key(work_id: str, filename: str) -> str:
    safe_work_id = quote(work_id.strip(), safe="")
    safe_filename = quote(filename.strip(), safe="")
    return f"{safe_work_id}/downloads/{safe_filename}"


def _archive_cdn_url(media_key: str) -> str:
    public_path = _MEDIA_SERVICE.public_path_for_key(media_key)
    media_cdn_base = _MEDIA_SERVICE.settings.media_cdn_base_url.strip()
    if media_cdn_base:
        return f"{media_cdn_base.rstrip('/')}{public_path}"
    return _MEDIA_SERVICE.media_url(public_path)


def _publish_download_archive(
    work_id: str,
    work: Mapping[str, object],
    archive_path: Path,
    export_key: str,
) -> tuple[str, str]:
    filename = _download_archive_filename(work_id, work, export_key)
    media_key = _archive_media_key(work_id, filename)
    if not _MEDIA_SERVICE.exists(media_key):
        _MEDIA_SERVICE.put_bytes(
            media_key,
            archive_path.read_bytes(),
            content_type="application/vnd.comicbook+zip",
        )
    return media_key, _archive_cdn_url(media_key)


def _build_cbz_export(
    work_id: str,
    work: Mapping[str, object],
    archive_path: Path,
) -> None:
    pages = list_work_page_rows(work_id)
    if not pages:
        raise ValueError("Work has no pages to export")

    chapters = list_work_chapters(work_id)
    page_order = [str(page.get("image_filename", "")) for page in pages]
    chapter_for_image: dict[str, str] = {}
    if chapters:
        assigned: set[str] = set()
        for chapter in chapters:
            chapter_index = _split_int(chapter.get("chapter_index", 0), 0)
            chapter_title = str(chapter.get("title", "Chapter")).strip()
            title = chapter_title if chapter_title else "Chapter"
            folder_name = _chapter_folder_name(chapter_index, title)
            members = _chapter_members_with_fallback(chapter, page_order)
            for image_name in members:
                if image_name in assigned:
                    continue
                chapter_for_image[image_name] = folder_name
                assigned.add(image_name)

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("ComicInfo.xml", _build_comicinfo_xml(work, pages))

        for page in pages:
            page_index = _split_int(page.get("page_index", 0), 0)
            image_filename = str(page.get("image_filename", "") if page.get("image_filename", "") else "").strip()
            if not image_filename:
                continue

            source_path = page_file_for(work_id, image_filename)
            if not source_path.exists():
                raise FileNotFoundError(f"Missing page image for export: {image_filename}")

            extension = source_path.suffix if source_path.suffix else ".avif"
            base_name = _safe_filename(
                f"{page_index:04d}{extension.lower()}",
                f"{page_index:04d}.avif",
            )
            if chapters:
                folder_name = _safe_filename(
                    chapter_for_image.get(image_filename, "unchaptered"),
                    "unchaptered",
                )
                arcname = f"{folder_name}/{base_name}"
            else:
                arcname = base_name

            archive.write(source_path, arcname=arcname)


def _ensure_download_archive(work_id: str, work: Mapping[str, object]) -> tuple[Path, str]:
    current_key = _current_export_key(work_id, work)
    archive_path = _resolve_archive_path(work_id, work, current_key)
    cache_path = _cache_meta_path(archive_path)
    cache_meta = _read_cache_meta(cache_path)

    cache_hit = (
        archive_path.exists() and cache_meta is not None and str(cache_meta.get("export_key", "")) == current_key
    )
    if cache_hit:
        return archive_path, current_key

    _build_cbz_export(work_id, work, archive_path)
    set_work_cbz_path(work_id, str(archive_path))
    _write_cache_meta(
        cache_path,
        {
            "work_id": work_id,
            "export_key": current_key,
            "archive_path": str(archive_path),
        },
    )
    return archive_path, current_key


def _version_page_files(
    version_manifest: dict[str, object],
    page_index: int,
) -> dict[str, str] | None:
    pages_obj = version_manifest.get("pages")
    if not isinstance(pages_obj, list):
        return None

    for page in cast(list[object], pages_obj):
        if not isinstance(page, dict):
            continue
        page_map = cast(dict[str, object], page)
        page_index_obj = page_map.get("page_index", 0)
        candidate_index = _split_int(page_index_obj, -1)
        if candidate_index != page_index:
            continue

        image_name = str(page_map.get("image_filename", "") if page_map.get("image_filename", "") else "").strip()
        thumb_name = str(page_map.get("thumb_filename", "") if page_map.get("thumb_filename", "") else "").strip()
        return {"image": image_name, "thumb": thumb_name}

    return None


def _manifest_with_media_urls(manifest: dict[str, object]) -> dict[str, object]:
    pages_obj = manifest.get("pages")
    if not isinstance(pages_obj, list):
        return manifest

    normalized_pages: list[dict[str, object]] = []
    for page_obj in cast(list[object], pages_obj):
        if not isinstance(page_obj, dict):
            normalized_pages.append({})
            continue
        page = dict(cast(dict[str, object], page_obj))
        image_url_raw = str(page.get("image_url", "")).strip()
        thumb_url_raw = str(page.get("thumb_url", "")).strip()
        if image_url_raw:
            page["image_url"] = media_url(image_url_raw)
        if thumb_url_raw:
            page["thumb_url"] = media_url(thumb_url_raw)
        normalized_pages.append(page)

    normalized_manifest = dict(manifest)
    normalized_manifest["pages"] = normalized_pages
    return normalized_manifest


def _version_manifest_with_media_urls(
    work_id: str,
    version_manifest: dict[str, object],
) -> dict[str, object]:
    pages_obj = version_manifest.get("pages")
    if not isinstance(pages_obj, list):
        return version_manifest

    normalized_pages: list[dict[str, object]] = []
    work_id_quoted = quote(work_id, safe="")
    for page_obj in cast(list[object], pages_obj):
        if not isinstance(page_obj, dict):
            normalized_pages.append({})
            continue
        page = dict(cast(dict[str, object], page_obj))

        image_url_raw = str(page.get("image_url", "")).strip()
        thumb_url_raw = str(page.get("thumb_url", "")).strip()
        image_filename = str(page.get("image_filename", "")).strip()
        thumb_filename = str(page.get("thumb_filename", "")).strip()

        if image_url_raw:
            page["image_url"] = media_url(image_url_raw)
        elif image_filename:
            page["image_url"] = media_url(f"/static/{work_id_quoted}/pages/{quote(image_filename, safe='/')}")

        if thumb_url_raw:
            page["thumb_url"] = media_url(thumb_url_raw)
        elif thumb_filename:
            page["thumb_url"] = media_url(f"/static/{work_id_quoted}/thumbs/{quote(thumb_filename, safe='/')}")
        elif image_filename:
            page["thumb_url"] = media_url(f"/static/{work_id_quoted}/pages/{quote(image_filename, safe='/')}")

        normalized_pages.append(page)

    normalized_manifest = dict(version_manifest)
    normalized_manifest["pages"] = normalized_pages
    return normalized_manifest


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    _ = request_id(request, response)
    tail = route_tail(request, ["api", "comic"])
    if tail is None:
        return json_response(response, {"detail": "Not found"}, 404)

    if tail == []:
        filters = {
            "q": request.args.get("q", ""),
            "fandom": request.args.get("fandom", ""),
            "tag": request.args.get("tag", ""),
            "rating": request.args.get("rating", ""),
            "status": request.args.get("status", ""),
        }
        works = [work for work in list_works(filters) if _can_view_work(request, work)]
        return json_response(response, {"works": works})

    work_id = tail[0]

    if len(tail) == 1:
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"work": work})

    if len(tail) == 2 and tail[1] == "manifest":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        manifest = get_manifest(work_id)
        if not manifest:
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"manifest": _manifest_with_media_urls(manifest)})

    if len(tail) == 2 and tail[1] == "versions":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"versions": list_work_versions(work_id)})

    if len(tail) == 3 and tail[1] == "versions":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        manifest = get_work_version_manifest(work_id, tail[2])
        if manifest is None:
            return json_response(response, {"detail": "Version not found"}, 404)
        return json_response(
            response,
            {"version": _version_manifest_with_media_urls(work_id, manifest)},
        )

    if len(tail) == 2 and tail[1] == "download":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)

        try:
            archive_path, export_key = _ensure_download_archive(work_id, work)
        except Exception as exc:
            log_exception(
                request,
                code="download_archive_build_failed",
                exc=exc,
                message="Failed to build download archive",
                extra={"work_id": work_id},
            )
            return stable_api_error(
                request,
                response,
                error="download_archive_build_failed",
                public_detail="Unable to build CBZ download archive",
                status_code=500,
                exc=exc,
            )

        try:
            _, archive_url = _publish_download_archive(
                work_id,
                work,
                archive_path,
                export_key,
            )
        except Exception as exc:
            log_exception(
                request,
                code="download_archive_publish_failed",
                exc=exc,
                message="Failed to publish download archive",
                extra={"work_id": work_id},
            )
            return stable_api_error(
                request,
                response,
                error="download_archive_publish_failed",
                public_detail="Unable to publish CBZ download archive",
                status_code=500,
                exc=exc,
            )

        return redirect_see_other(response, archive_url)

    if len(tail) == 4 and tail[1] == "pages":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)

        try:
            page_index = int(tail[2])
        except ValueError:
            return json_response(response, {"detail": "Page not found"}, 404)

        version_id = request.args.get("version_id", "").strip()
        page: dict[str, str] | None
        if version_id:
            version_manifest = get_work_version_manifest(work_id, version_id)
            if version_manifest is None:
                return json_response(response, {"detail": "Version not found"}, 404)
            page = _version_page_files(version_manifest, page_index)
        else:
            page = get_page_files(work_id, page_index)
        if not page:
            return json_response(response, {"detail": "Page not found"}, 404)

        if tail[3] == "image":
            image_name = page.get("image")
            if not image_name:
                return json_response(response, {"detail": "Page image missing"}, 404)
            return send_file(response, page_file_for(work_id, image_name))

        if tail[3] == "thumb":
            thumb_name = page.get("thumb")
            if not thumb_name:
                return json_response(response, {"detail": "Page thumb not found"}, 404)
            return send_file(response, thumb_file_for(work_id, thumb_name))

    if len(tail) == 2 and tail[1] == "progress":
        user_id = request.args.get("user_id", "anon")
        return json_response(response, {"page_index": load_progress(work_id, user_id)})

    return json_response(response, {"detail": "Not found"}, 404)
