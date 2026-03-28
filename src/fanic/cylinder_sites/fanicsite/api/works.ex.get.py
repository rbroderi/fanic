import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED
from zipfile import ZipFile

from pathvalidate import sanitize_filename

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import log_exception
from fanic.cylinder_sites.common import page_file_for
from fanic.cylinder_sites.common import request_id
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import send_file
from fanic.cylinder_sites.common import stable_api_error
from fanic.cylinder_sites.common import thumb_file_for
from fanic.repository import can_view_work
from fanic.repository import get_manifest
from fanic.repository import get_page_files
from fanic.repository import get_work
from fanic.repository import get_work_version_manifest
from fanic.repository import list_work_chapter_members
from fanic.repository import list_work_chapters
from fanic.repository import list_work_page_rows
from fanic.repository import list_work_versions
from fanic.repository import list_works
from fanic.repository import load_progress
from fanic.repository import set_work_cbz_path
from fanic.settings import CBZ_DIR
from fanic.utils import slugify


def _can_view_work(request: RequestLike, work: dict[str, object]) -> bool:
    return can_view_work(current_user(request), work)


def _csv_join(values: list[str]) -> str:
    return ", ".join(value for value in values if value.strip())


def _split_csv_field(value: object) -> list[str]:
    if isinstance(value, list):
        normalized: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    text_value = str(value if value else "").strip()
    if not text_value:
        return []
    return [part.strip() for part in text_value.split(",") if part.strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


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


def _fanic_scaninformation(work: dict[str, object]) -> str:
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


def _extract_tag_names(work: dict[str, object], tag_type: str) -> list[str]:
    tags_obj = work.get("tags")
    if not isinstance(tags_obj, list):
        return []
    names: list[str] = []
    for tag in tags_obj:
        if not isinstance(tag, dict):
            continue
        if str(tag.get("type", "")) != tag_type:
            continue
        name = str(tag.get("name", "")).strip()
        if name:
            names.append(name)
    return names


def _build_comicinfo_xml(work: dict[str, object], pages: list[dict[str, object]]) -> str:
    root = ET.Element("ComicInfo")

    def add_text_element(name: str, value: str) -> None:
        ET.SubElement(root, name).text = value

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
    pages_element = ET.SubElement(root, "Pages")
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

        ET.SubElement(pages_element, "Page", attrib=page_attrs)

    main_character = character_names[0] if character_names else ""
    if main_character:
        add_text_element("MainCharacterOrTeam", main_character)

    if warning_names:
        add_text_element("Review", _csv_join(warning_names))

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


def _chapter_members_with_fallback(
    chapter: dict[str, object],
    page_order: list[str],
) -> list[str]:
    chapter_id = int(chapter.get("id", 0) if chapter.get("id", 0) else 0)
    members = list_work_chapter_members(chapter_id)
    if members:
        return [name for name in members if name in page_order]

    start_page = int(chapter.get("start_page", 1) if chapter.get("start_page", 1) else 1)
    end_page = int(chapter.get("end_page", start_page) if chapter.get("end_page", start_page) else start_page)
    start_page = max(1, min(start_page, len(page_order) if len(page_order) else 1))
    end_page = max(
        start_page,
        min(end_page, len(page_order) if len(page_order) else start_page),
    )
    return page_order[start_page - 1 : end_page]


def _chapter_folder_name(chapter_index: int, title: str) -> str:
    base_slug = slugify(title)
    base = base_slug if base_slug else "chapter"
    return _safe_filename(f"chapter-{chapter_index:03d}-{base}", "chapter")


def _safe_filename(name: str, fallback: str) -> str:
    safe = sanitize_filename(name, replacement_text="_").strip(" .")
    return safe if safe else fallback


def _current_export_key(work_id: str, work: dict[str, object]) -> str:
    versions = list_work_versions(work_id, limit=1)
    if versions:
        return f"version:{str(versions[0].get('version_id', ''))}"
    updated_at = str(work.get("updated_at", ""))
    page_count = int(work.get("page_count", 0) if work.get("page_count", 0) else 0)
    return f"legacy:{updated_at}:{page_count}"


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
    return raw


def _write_cache_meta(cache_path: Path, payload: dict[str, object]) -> None:
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _resolve_archive_path(work_id: str, work: dict[str, object]) -> Path:
    cbz_path = str(work.get("cbz_path", "") if work.get("cbz_path", "") else "").strip()
    if cbz_path:
        return Path(cbz_path)
    return CBZ_DIR / f"{work_id}.cbz"


def _build_cbz_export(work_id: str, work: dict[str, object], archive_path: Path) -> None:
    pages = list_work_page_rows(work_id)
    if not pages:
        raise ValueError("Work has no pages to export")

    chapters = list_work_chapters(work_id)
    page_order = [str(page.get("image_filename", "")) for page in pages]
    chapter_for_image: dict[str, str] = {}
    if chapters:
        assigned: set[str] = set()
        for chapter in chapters:
            chapter_index = int(chapter.get("chapter_index", 0) if chapter.get("chapter_index", 0) else 0)
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
            page_index = int(page.get("page_index", 0) if page.get("page_index", 0) else 0)
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


def _ensure_download_archive(work_id: str, work: dict[str, object]) -> Path:
    archive_path = _resolve_archive_path(work_id, work)
    current_key = _current_export_key(work_id, work)
    cache_path = _cache_meta_path(archive_path)
    cache_meta = _read_cache_meta(cache_path)

    cache_hit = (
        archive_path.exists() and cache_meta is not None and str(cache_meta.get("export_key", "")) == current_key
    )
    if cache_hit:
        return archive_path

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
    return archive_path


def _version_page_files(
    version_manifest: dict[str, object],
    page_index: int,
) -> dict[str, str] | None:
    pages_obj = version_manifest.get("pages")
    if not isinstance(pages_obj, list):
        return None

    for page in pages_obj:
        if not isinstance(page, dict):
            continue
        page_index_obj = page.get("page_index", 0)
        try:
            candidate_index = int(page_index_obj)
        except (TypeError, ValueError):
            continue
        if candidate_index != page_index:
            continue

        image_name = str(page.get("image_filename", "") if page.get("image_filename", "") else "").strip()
        thumb_name = str(page.get("thumb_filename", "") if page.get("thumb_filename", "") else "").strip()
        return {"image": image_name, "thumb": thumb_name}

    return None


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    _ = request_id(request, response)
    tail = route_tail(request, ["api", "works"])
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
        return json_response(response, {"manifest": manifest})

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
        return json_response(response, {"version": manifest})

    if len(tail) == 2 and tail[1] == "download":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)

        try:
            archive_path = _ensure_download_archive(work_id, work)
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

        slug = work.get("slug")
        requested_name = f"{slug}.cbz" if isinstance(slug, str) else f"{work_id}.cbz"
        filename = _safe_filename(requested_name, f"{work_id}.cbz")
        return send_file(response, archive_path, filename)

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
