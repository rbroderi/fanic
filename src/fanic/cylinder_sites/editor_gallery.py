import re
from collections.abc import Mapping
from collections.abc import Sequence
from html import escape
from pathlib import Path
from urllib.parse import quote

from fanic.cylinder_sites.common.responses import media_url
from fanic.repository.works import list_work_chapter_members

_NATURAL_SORT_RE = re.compile(r"(\d+)")


def _to_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _natural_filename_sort_key(filename: str) -> tuple[object, ...]:
    parts = _NATURAL_SORT_RE.split(Path(filename).name.lower())
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        elif part:
            key.append(part)
    return tuple(key)


def _chapter_seed_members_from_range(page_order: list[str], chapter: Mapping[str, object]) -> list[str]:
    start_page_raw = chapter.get("start_page", 1)
    start_page = _to_int(start_page_raw, 1)
    end_page_raw = chapter.get("end_page", start_page)
    end_page = _to_int(end_page_raw, start_page)
    page_order_len_or_one = len(page_order) if len(page_order) else 1
    start_page = max(1, min(start_page, page_order_len_or_one))
    end_page = max(
        start_page,
        min(end_page, len(page_order) if len(page_order) else start_page),
    )
    return page_order[start_page - 1 : end_page]


def _page_thumb_button_html(
    work_id: str,
    page_by_filename: dict[str, Mapping[str, object]],
    image_filename: str,
) -> str:
    page = page_by_filename.get(image_filename)
    if not page:
        return ""

    page_index_raw = page.get("page_index", 0)
    page_index = _to_int(page_index_raw, 0)
    thumb_obj = page.get("thumb_filename")
    image_obj = page.get("image_filename", "")
    thumb_name = str(thumb_obj).strip().lstrip("/") if thumb_obj else ""
    if not thumb_name:
        thumb_name = str(image_obj).strip().lstrip("/")
    work_id_url = quote(work_id, safe="")
    thumb_url = media_url(f"/static/{work_id_url}/thumbs/{quote(thumb_name, safe='/')}")
    safe_name = escape(image_filename)
    safe_thumb_url = escape(thumb_url)
    return (
        '<button type="button" class="page-thumb-card" '
        f'draggable="true" data-image-filename="{safe_name}" '
        f'data-page-index="{page_index}">'
        f'<img src="{safe_thumb_url}" alt="Page {page_index}" loading="lazy" />'
        f"<span>Page {page_index}</span>"
        "</button>"
    )


def render_editor_page_gallery_html(
    work_id: str,
    pages: Sequence[Mapping[str, object]],
    chapters: Sequence[Mapping[str, object]],
) -> str:
    if not work_id:
        return ""
    if not pages:
        return '<p class="profile-meta">No pages uploaded yet.</p>'

    ordered_pages = sorted(
        pages,
        key=lambda page: (
            _to_int(page.get("page_index", 0), 0),
            _natural_filename_sort_key(str(page.get("image_filename", ""))),
        ),
    )

    page_by_filename: dict[str, Mapping[str, object]] = {}
    page_order: list[str] = []
    for page in ordered_pages:
        image_filename = str(page.get("image_filename", "")).strip()
        if not image_filename:
            continue
        page_by_filename[image_filename] = page
        page_order.append(image_filename)

    assigned: set[str] = set()
    section_parts: list[str] = []

    for chapter in chapters:
        chapter_id_raw = chapter.get("id", 0)
        chapter_id = _to_int(chapter_id_raw, 0)
        chapter_index_raw = chapter.get("chapter_index", 0)
        chapter_index = _to_int(chapter_index_raw, 0)
        title = escape(str(chapter.get("title", "Untitled Chapter")))
        members = list_work_chapter_members(chapter_id)
        if not members:
            members = _chapter_seed_members_from_range(page_order, chapter)

        member_set = {name for name in members if name in page_by_filename}
        ordered_members = [name for name in page_order if name in member_set and name not in assigned]
        assigned.update(ordered_members)

        thumbs_html = "".join(
            _page_thumb_button_html(work_id, page_by_filename, image_filename) for image_filename in ordered_members
        )
        section_parts.append(
            '<section class="chapter-gallery-section" '
            f'data-chapter-id="{chapter_id}">'
            f"<h4>Chapter {chapter_index}: {title}</h4>"
            '<div class="page-gallery-grid">'
            f"{thumbs_html}"
            "</div></section>"
        )

    unchaptered = [name for name in page_order if name not in assigned]
    unchaptered_html = "".join(
        _page_thumb_button_html(work_id, page_by_filename, image_filename) for image_filename in unchaptered
    )
    section_parts.append(
        '<section class="chapter-gallery-section" data-chapter-id="">'
        "<h4>Unchaptered</h4>"
        f'<div class="page-gallery-grid">{unchaptered_html}</div>'
        "</section>"
    )

    return "".join(section_parts)


def render_editor_chapters_html(
    work_id: str,
    chapters: Sequence[Mapping[str, object]],
    *,
    form_action: str,
    action_field_name: str,
    update_action_value: str,
    delete_action_value: str,
    delete_confirm_message: str | None = None,
) -> str:
    if not work_id:
        return ""
    if not chapters:
        return '<p class="profile-meta">No chapters yet.</p>'

    confirm_attr = f' data-confirm-message="{escape(delete_confirm_message)}"' if delete_confirm_message else ""

    rows: list[str] = []
    for chapter in chapters:
        chapter_id_raw = chapter.get("id", 0)
        chapter_id = _to_int(chapter_id_raw, 0)
        chapter_index_raw = chapter.get("chapter_index", 0)
        chapter_index = _to_int(chapter_index_raw, 0)
        title = escape(str(chapter.get("title", "Untitled Chapter")))
        start_page_raw = chapter.get("start_page", 1)
        start_page = _to_int(start_page_raw, 1)
        end_page_raw = chapter.get("end_page", start_page)
        end_page = _to_int(end_page_raw, start_page)
        form_action_esc = escape(form_action)
        action_field_esc = escape(action_field_name)
        update_action_esc = escape(update_action_value)
        delete_action_esc = escape(delete_action_value)
        work_id_esc = escape(work_id)
        title_input_id = f"chapter-title-{chapter_id}"
        start_input_id = f"chapter-start-{chapter_id}"
        end_input_id = f"chapter-end-{chapter_id}"
        rows.append(
            f"""
            <article class="card info-card editor-row">
                <p><strong>Chapter {chapter_index}: {title}</strong> (pages {start_page}-{end_page})</p>
                <form class="upload-form" method="post" action="{form_action_esc}">
                    <input type="hidden" name="{action_field_esc}" value="{update_action_esc}" />
                    <input type="hidden" name="editor_work_id" value="{work_id_esc}" />
                    <input type="hidden" name="chapter_id" value="{chapter_id}" />
                    <label for="{title_input_id}">Title</label>
                    <input id="{title_input_id}" type="text" name="chapter_title" value="{title}" required />
                    <label for="{start_input_id}">Start page</label>
                    <input id="{start_input_id}" type="number" name="chapter_start_page" min="1" value="{start_page}" required />
                    <label for="{end_input_id}">End page</label>
                    <input id="{end_input_id}" type="number" name="chapter_end_page" min="1" value="{end_page}" required />
                    <button type="submit">Update chapter</button>
                </form>
                <form class="upload-form" method="post" action="{form_action_esc}"{confirm_attr}>
                    <input type="hidden" name="{action_field_esc}" value="{delete_action_esc}" />
                    <input type="hidden" name="editor_work_id" value="{work_id_esc}" />
                    <input type="hidden" name="chapter_id" value="{chapter_id}" />
                    <button type="submit" class="button-muted">Delete chapter</button>
                </form>
            </article>
            """
        )
    return "".join(rows)
