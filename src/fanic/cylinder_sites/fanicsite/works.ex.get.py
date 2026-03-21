from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import (
    ADMIN_USERNAME,
    RequestLike,
    ResponseLike,
    current_user,
    rating_badge_html,
    render_html_template,
    route_tail,
    text_error,
)
from fanic.repository import (
    can_view_work,
    get_work,
    has_user_kudoed_work,
    list_tag_names,
    list_work_chapter_members,
    list_work_chapters,
    list_work_comments,
    list_work_page_rows,
    work_kudos_count,
)

RATING_CHOICES = [
    "Not Rated",
    "General Audiences",
    "Teen And Up Audiences",
    "Mature",
    "Explicit",
]


def _can_edit_work(username: str, uploader_username: str) -> bool:
    return bool(username) and (
        username == uploader_username or username == ADMIN_USERNAME
    )


def _tag_names_csv(tags: object, tag_type: str) -> str:
    if not isinstance(tags, list):
        return ""
    names: list[str] = []
    for tag in tags:
        if not isinstance(tag, dict):
            continue
        if str(tag.get("type", "")) != tag_type:
            continue
        name = str(tag.get("name", "")).strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def _options_html(names: list[str], selected: str) -> str:
    selected_norm = selected.strip().casefold()
    parts: list[str] = []
    for name in names:
        selected_attr = " selected" if name.strip().casefold() == selected_norm else ""
        parts.append(
            f'<option value="{escape(name)}"{selected_attr}>{escape(name)}</option>'
        )
    return "".join(parts)


def _datalist_options_html(tag_type: str) -> str:
    return "".join(
        f'<option value="{escape(name)}"></option>' for name in list_tag_names(tag_type)
    )


def _comment_cards_html(comments: list[dict[str, object]]) -> str:
    if not comments:
        return '<p class="profile-meta">No comments yet.</p>'

    parts: list[str] = []
    for comment in comments:
        username = escape(str(comment.get("username", "anon")))
        created_at = escape(str(comment.get("created_at", "")))
        chapter_number = comment.get("chapter_number")
        if chapter_number is None:
            scope = "Overall"
        else:
            scope = f"Chapter {escape(str(chapter_number))}"
        body = escape(str(comment.get("body", ""))).replace("\n", "<br />")
        parts.append(
            f'<article class="card comment-card"><p class="comment-meta"><strong>{scope}</strong> by {username} on {created_at}</p><p>{body}</p></article>'
        )
    return "".join(parts)


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


def _page_gallery_html(
    work_id: str,
    pages: list[dict[str, object]],
    chapters: list[dict[str, object]],
) -> str:
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


def _editor_chapters_html(work_id: str, chapters: list[dict[str, object]]) -> str:
    if not chapters:
        return '<p class="profile-meta">No chapters yet.</p>'

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
                <form class="upload-form" method="post" action="/works/{work_id}/edit">
                    <input type="hidden" name="edit_action" value="editor-update-chapter" />
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
                <form class="upload-form" method="post" action="/works/{work_id}/edit" onsubmit="return confirm('Delete this chapter?');">
                    <input type="hidden" name="edit_action" value="editor-delete-chapter" />
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
                work_id=escape(work_id),
                chapter_id=chapter_id,
            )
        )
    return "".join(rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["works"])
    if tail is None:
        return text_error(response, "Not found", 404)

    if len(tail) == 2 and tail[1] == "edit":
        work_id = tail[0]
        work = get_work(work_id)
        if not work:
            return text_error(response, "Work not found", 404)

        username = current_user(request)
        if not can_view_work(username, work):
            return text_error(response, "Work not found", 404)

        uploader = str(work.get("uploader_username") or "")
        if not _can_edit_work(username, uploader):
            return text_error(response, "Forbidden", 403)

        tags = work.get("tags", [])
        warnings_text = _tag_names_csv(tags, "archive_warning") or str(
            work.get("warnings", "")
        )

        save_msg = request.args.get("msg", "").strip()
        if save_msg == "saved":
            status_text = "Metadata saved."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-added":
            status_text = "Page uploaded."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-added-rating-elevated":
            status_text = (
                "Page uploaded. Rating auto-elevated based on moderation detection."
            )
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-replaced":
            status_text = "Page replaced."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-replaced-rating-elevated":
            status_text = (
                "Page replaced. Rating auto-elevated based on moderation detection."
            )
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-deleted":
            status_text = "Page deleted."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-moved":
            status_text = "Page moved."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "page-reordered":
            status_text = (
                "Gallery order saved. Page order and chapter assignments updated."
            )
            status_class = "success"
            status_hidden = ""
        elif save_msg == "chapter-added":
            status_text = "Chapter added."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "chapter-updated":
            status_text = "Chapter updated."
            status_class = "success"
            status_hidden = ""
        elif save_msg == "chapter-deleted":
            status_text = "Chapter deleted."
            status_class = "success"
            status_hidden = ""
        elif save_msg in {
            "page-file-required",
            "page-add-failed",
            "page-replace-failed",
            "page-delete-failed",
            "page-move-failed",
            "page-reorder-failed",
            "chapter-add-failed",
            "chapter-update-failed",
            "chapter-delete-failed",
        }:
            status_text = "Edit action failed. Check inputs and permissions."
            status_class = "error"
            status_hidden = ""
        elif save_msg == "page-blocked":
            status_text = "Upload blocked by moderation policy (photorealistic images are not allowed)."
            status_class = "error"
            status_hidden = ""
        else:
            status_text = ""
            status_class = ""
            status_hidden = "hidden"

        pages = list_work_page_rows(work_id)
        chapters = list_work_chapters(work_id)

        return render_html_template(
            request,
            response,
            "work-edit.html",
            {
                "__WORK_ID__": escape(work_id),
                "__EDIT_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDIT_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDIT_RATING_OPTIONS_HTML__": _options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDIT_WARNINGS__": escape(warnings_text),
                "__EDIT_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDIT_SERIES__": escape(str(work.get("series_name", "") or "")),
                "__EDIT_SERIES_INDEX__": escape(
                    str(work.get("series_index", "") or "")
                ),
                "__EDIT_PUBLISHED_AT__": escape(
                    str(work.get("published_at", "") or "")
                ),
                "__EDIT_FANDOMS__": escape(_tag_names_csv(tags, "fandom")),
                "__EDIT_RELATIONSHIPS__": escape(_tag_names_csv(tags, "relationship")),
                "__EDIT_CHARACTERS__": escape(_tag_names_csv(tags, "character")),
                "__EDIT_FREEFORM_TAGS__": escape(_tag_names_csv(tags, "freeform")),
                "__STATUS_IN_PROGRESS_SELECTED__": _selected_attr(
                    str(work.get("status", "in_progress")), "in_progress"
                ),
                "__STATUS_COMPLETE_SELECTED__": _selected_attr(
                    str(work.get("status", "in_progress")), "complete"
                ),
                "__EDIT_STATUS_TEXT__": status_text,
                "__EDIT_STATUS_CLASS__": status_class,
                "__EDIT_STATUS_HIDDEN_ATTR__": status_hidden,
                "__EDITOR_WORK_ID__": escape(work_id),
                "__EDITOR_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDITOR_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDITOR_RATING_OPTIONS_HTML__": _options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDITOR_STATUS_IN_PROGRESS_SELECTED__": _selected_attr(
                    str(work.get("status", "in_progress")), "in_progress"
                ),
                "__EDITOR_STATUS_COMPLETE_SELECTED__": _selected_attr(
                    str(work.get("status", "in_progress")), "complete"
                ),
                "__EDITOR_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDITOR_PAGE_GALLERY_HTML__": _page_gallery_html(
                    work_id,
                    pages,
                    chapters,
                ),
                "__EDITOR_CHAPTERS_HTML__": _editor_chapters_html(work_id, chapters),
                "__WARNINGS_OPTIONS_HTML__": _datalist_options_html("archive_warning"),
                "__FANDOM_OPTIONS_HTML__": _datalist_options_html("fandom"),
                "__RELATIONSHIP_OPTIONS_HTML__": _datalist_options_html("relationship"),
                "__CHARACTER_OPTIONS_HTML__": _datalist_options_html("character"),
                "__FREEFORM_OPTIONS_HTML__": _datalist_options_html("freeform"),
            },
        )

    if len(tail) != 1:
        return text_error(response, "Not found", 404)

    work_id = tail[0]
    work = get_work(work_id)
    if not work:
        return text_error(response, "Work not found", 404)

    username = current_user(request)
    if not can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    title = escape(str(work.get("title", "Untitled")))
    summary = escape(str(work.get("summary", "") or "No summary provided."))
    rating_html = rating_badge_html(work.get("rating", "Not Rated"))
    status = escape(str(work.get("status", "in_progress")))
    page_count = escape(str(work.get("page_count", 0)))
    cover_index = escape(str(work.get("cover_page_index", 1)))

    tags = work.get("tags", [])
    tag_html = ""
    if isinstance(tags, list):
        rendered_tags: list[str] = []
        for tag in tags:
            if isinstance(tag, dict):
                tag_type = escape(str(tag.get("type", "tag")))
                tag_name = escape(str(tag.get("name", "")))
                rendered_tags.append(f'<span class="tag">{tag_type}: {tag_name}</span>')
        tag_html = "".join(rendered_tags)

    uploader = str(work.get("uploader_username") or "")
    can_edit = _can_edit_work(username, uploader)
    can_delete = username == ADMIN_USERNAME
    comments = list_work_comments(work_id)
    kudos = work_kudos_count(work_id)
    has_kudoed = has_user_kudoed_work(work_id, username)

    msg = request.args.get("msg", "").strip()
    if msg == "comment-saved":
        work_status_text = "Comment posted."
        work_status_class = "success"
        work_status_hidden = ""
    elif msg == "kudos-saved":
        work_status_text = "Kudos sent."
        work_status_class = "success"
        work_status_hidden = ""
    elif msg == "already-kudoed":
        work_status_text = "You already left kudos for this work."
        work_status_class = ""
        work_status_hidden = ""
    elif msg == "login-required":
        work_status_text = "Login required to leave comments or kudos."
        work_status_class = "error"
        work_status_hidden = ""
    elif msg == "comment-empty":
        work_status_text = "Comment cannot be empty."
        work_status_class = "error"
        work_status_hidden = ""
    elif msg == "chapter-invalid":
        work_status_text = "Chapter number must be between 1 and page count."
        work_status_class = "error"
        work_status_hidden = ""
    else:
        work_status_text = ""
        work_status_class = ""
        work_status_hidden = "hidden"

    return render_html_template(
        request,
        response,
        "work.html",
        {
            "__WORK_TITLE__": title,
            "__WORK_SUMMARY__": summary,
            "__WORK_META__": f"{rating_html} | {status} | {page_count} pages",
            "__WORK_COVER_SRC__": f"/api/works/{escape(work_id)}/pages/{cover_index}/image",
            "__WORK_READ_HREF__": f"/reader/{escape(work_id)}",
            "__WORK_DOWNLOAD_HREF__": f"/api/works/{escape(work_id)}/download",
            "__WORK_TAGS_HTML__": tag_html,
            "__EDIT_METADATA_HREF__": f"/works/{escape(work_id)}/edit",
            "__EDIT_METADATA_HIDDEN_ATTR__": "" if can_edit else "hidden",
            "__ADMIN_DELETE_HIDDEN_ATTR__": "" if can_delete else "hidden",
            "__WORK_ID__": escape(work_id),
            "__WORK_KUDOS_COUNT__": escape(str(kudos)),
            "__KUDOS_DISABLED_ATTR__": "disabled"
            if (not username or has_kudoed)
            else "",
            "__WORK_STATUS_TEXT__": work_status_text,
            "__WORK_STATUS_CLASS__": work_status_class,
            "__WORK_STATUS_HIDDEN_ATTR__": work_status_hidden,
            "__COMMENTS_HTML__": _comment_cards_html(comments),
        },
    )
