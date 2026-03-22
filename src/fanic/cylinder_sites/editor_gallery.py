from __future__ import annotations

from html import escape

from fanic.repository import list_work_chapter_members


def _chapter_seed_members_from_range(
    page_order: list[str], chapter: dict[str, object]
) -> list[str]:
    start_page = int(chapter.get("start_page", 1) or 1)
    end_page = int(chapter.get("end_page", start_page) or start_page)
    start_page = max(1, min(start_page, len(page_order) or 1))
    end_page = max(start_page, min(end_page, len(page_order) or start_page))
    return page_order[start_page - 1 : end_page]


def _page_thumb_button_html(
    work_id: str,
    page_by_filename: dict[str, dict[str, object]],
    image_filename: str,
) -> str:
    page = page_by_filename.get(image_filename)
    if not page:
        return ""

    page_index = int(page.get("page_index", 0) or 0)
    safe_name = escape(image_filename)
    safe_work_id = escape(work_id)
    return (
        '<button type="button" class="page-thumb-card" '
        f'draggable="true" data-image-filename="{safe_name}" '
        f'data-page-index="{page_index}">'
        f'<img src="/api/works/{safe_work_id}/pages/{page_index}/thumb" alt="Page {page_index}" loading="lazy" />'
        f"<span>Page {page_index}</span>"
        "</button>"
    )


def render_editor_page_gallery_html(
    work_id: str,
    pages: list[dict[str, object]],
    chapters: list[dict[str, object]],
) -> str:
    if not work_id:
        return ""
    if not pages:
        return '<p class="profile-meta">No pages uploaded yet.</p>'

    page_by_filename: dict[str, dict[str, object]] = {}
    page_order: list[str] = []
    for page in pages:
        image_filename = str(page.get("image_filename", "")).strip()
        if not image_filename:
            continue
        page_by_filename[image_filename] = page
        page_order.append(image_filename)

    assigned: set[str] = set()
    section_parts: list[str] = []

    for chapter in chapters:
        chapter_id = int(chapter.get("id", 0) or 0)
        chapter_index = int(chapter.get("chapter_index", 0) or 0)
        title = escape(str(chapter.get("title", "Untitled Chapter")))
        members = list_work_chapter_members(chapter_id)
        if not members:
            members = _chapter_seed_members_from_range(page_order, chapter)

        member_set = {name for name in members if name in page_by_filename}
        ordered_members = [
            name for name in page_order if name in member_set and name not in assigned
        ]
        assigned.update(ordered_members)

        thumbs_html = "".join(
            _page_thumb_button_html(work_id, page_by_filename, image_filename)
            for image_filename in ordered_members
        )
        section_parts.append(
            (
                '<section class="chapter-gallery-section" '
                f'data-chapter-id="{chapter_id}">'
                f"<h4>Chapter {chapter_index}: {title}</h4>"
                '<div class="page-gallery-grid">'
                f"{thumbs_html}"
                "</div></section>"
            )
        )

    unchaptered = [name for name in page_order if name not in assigned]
    unchaptered_html = "".join(
        _page_thumb_button_html(work_id, page_by_filename, image_filename)
        for image_filename in unchaptered
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
    chapters: list[dict[str, object]],
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

    confirm_attr = (
        f" onsubmit=\"return confirm('{escape(delete_confirm_message)}');\""
        if delete_confirm_message
        else ""
    )

    rows: list[str] = []
    for chapter in chapters:
        chapter_id = int(chapter.get("id", 0) or 0)
        chapter_index = int(chapter.get("chapter_index", 0) or 0)
        title = escape(str(chapter.get("title", "Untitled Chapter")))
        start_page = int(chapter.get("start_page", 1) or 1)
        end_page = int(chapter.get("end_page", start_page) or start_page)
        rows.append(
            """
            <article class="card info-card editor-row">
                <p><strong>Chapter {chapter_index}: {title}</strong> (pages {start_page}-{end_page})</p>
                <form class="upload-form" method="post" action="{form_action}">
                    <input type="hidden" name="{action_field_name}" value="{update_action_value}" />
                    <input type="hidden" name="editor_work_id" value="{work_id}" />
                    <input type="hidden" name="chapter_id" value="{chapter_id}" />
                    <label>Title</label>
                    <input type="text" name="chapter_title" value="{title}" required />
                    <label>Start page</label>
                    <input type="number" name="chapter_start_page" min="1" value="{start_page}" required />
                    <label>End page</label>
                    <input type="number" name="chapter_end_page" min="1" value="{end_page}" required />
                    <button type="submit">Update chapter</button>
                </form>
                <form class="upload-form" method="post" action="{form_action}"{delete_confirm_attr}>
                    <input type="hidden" name="{action_field_name}" value="{delete_action_value}" />
                    <input type="hidden" name="editor_work_id" value="{work_id}" />
                    <input type="hidden" name="chapter_id" value="{chapter_id}" />
                    <button type="submit" class="button-muted">Delete chapter</button>
                </form>
            </article>
            """.format(
                chapter_index=chapter_index,
                title=title,
                start_page=start_page,
                end_page=end_page,
                form_action=escape(form_action),
                action_field_name=escape(action_field_name),
                update_action_value=escape(update_action_value),
                delete_action_value=escape(delete_action_value),
                work_id=escape(work_id),
                chapter_id=chapter_id,
                delete_confirm_attr=confirm_attr,
            )
        )
    return "".join(rows)
