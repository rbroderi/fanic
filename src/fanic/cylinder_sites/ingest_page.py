from __future__ import annotations

import json
from html import escape
from typing import Any

from fanic.cylinder_sites.common import (
    STATIC_ROOT,
    RequestLike,
    ResponseLike,
    current_user,
    user_menu_replacements,
)
from fanic.repository import list_tag_names

RATING_CHOICES = [
    "Not Rated",
    "General Audiences",
    "Teen And Up Audiences",
    "Mature",
    "Explicit",
]


def _as_csv(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, str):
        return value
    return ""


def _status_class(kind: str) -> str:
    if kind == "error":
        return "error"
    if kind == "success":
        return "success"
    return ""


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


def _editor_pages_html(work_id: str, pages: list[dict[str, object]]) -> str:
    if not work_id:
        return ""
    if not pages:
        return '<p class="profile-meta">No pages uploaded yet.</p>'

    rows: list[str] = []
    for page in pages:
        page_index = int(page.get("page_index", 0) or 0)
        image_filename = escape(str(page.get("image_filename", "")))
        rows.append(
            """
                        <article class="card info-card editor-row">
                            <p><strong>Page {page_index}</strong> ({image_filename})</p>
                            <form class="upload-form" method="post" enctype="multipart/form-data" action="/ingest">
                                <input type="hidden" name="action" value="editor-replace-page" />
                                <input type="hidden" name="editor_work_id" value="{work_id}" />
                                <input type="hidden" name="page_index" value="{page_index}" />
                                <label>Replace with image</label>
                                <input type="file" name="page_image" accept="image/*" required />
                                <button type="submit">Replace page</button>
                            </form>
                            <form class="upload-form" method="post" action="/ingest">
                                <input type="hidden" name="action" value="editor-move-page" />
                                <input type="hidden" name="editor_work_id" value="{work_id}" />
                                <input type="hidden" name="from_index" value="{page_index}" />
                                <label>Move to position</label>
                                <input type="number" name="to_index" min="1" required />
                                <button type="submit">Move page</button>
                            </form>
                            <form class="upload-form" method="post" action="/ingest">
                                <input type="hidden" name="action" value="editor-delete-page" />
                                <input type="hidden" name="editor_work_id" value="{work_id}" />
                                <input type="hidden" name="page_index" value="{page_index}" />
                                <button type="submit" class="button-muted">Delete page</button>
                            </form>
                        </article>
                        """.format(
                page_index=page_index,
                image_filename=image_filename,
                work_id=escape(work_id),
            )
        )
    return "".join(rows)


def _editor_chapters_html(work_id: str, chapters: list[dict[str, object]]) -> str:
    if not work_id:
        return ""
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
                            <form class="upload-form" method="post" action="/ingest">
                                <input type="hidden" name="action" value="editor-update-chapter" />
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
                            <form class="upload-form" method="post" action="/ingest">
                                <input type="hidden" name="action" value="editor-delete-chapter" />
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


def render_ingest_page(
    request: RequestLike,
    response: ResponseLike,
    *,
    metadata: dict[str, object] | None = None,
    show_metadata_form: bool = False,
    upload_token: str = "",
    editor_work_id: str = "",
    editor_title: str = "",
    editor_summary: str = "",
    editor_rating: str = "Not Rated",
    editor_status: str = "in_progress",
    editor_language: str = "en",
    editor_pages: list[dict[str, object]] | None = None,
    editor_chapters: list[dict[str, object]] | None = None,
    ingest_status: str = "",
    ingest_status_kind: str = "",
    result_payload: dict[str, object] | None = None,
) -> ResponseLike:
    user = current_user(request)
    logged_in = user is not None

    data = metadata or {}
    pages = editor_pages or []
    chapters = editor_chapters or []
    ingest_html = (STATIC_ROOT / "ingest.html").read_text(encoding="utf-8")

    replacements = {
        "__LOGIN_REQUIRED_HIDDEN_ATTR__": "hidden" if logged_in else "",
        "__UPLOAD_HIDDEN_ATTR__": "" if logged_in else "hidden",
        "__AUTH_STATUS__": f"Logged in as {user}."
        if logged_in and user
        else "Not logged in.",
        "__AUTH_STATUS_CLASS__": "" if logged_in else "error",
        "__METADATA_FORM_HIDDEN_ATTR__": "" if show_metadata_form else "hidden",
        "__UPLOAD_TOKEN__": escape(upload_token),
        "__EDITOR_WORK_ID__": escape(editor_work_id),
        "__EDITOR_TITLE__": escape(editor_title),
        "__EDITOR_SUMMARY__": escape(editor_summary),
        "__EDITOR_RATING_OPTIONS_HTML__": _options_html(RATING_CHOICES, editor_rating),
        "__EDITOR_STATUS_IN_PROGRESS_SELECTED__": "selected"
        if editor_status == "in_progress"
        else "",
        "__EDITOR_STATUS_COMPLETE_SELECTED__": "selected"
        if editor_status == "complete"
        else "",
        "__EDITOR_LANGUAGE__": escape(editor_language),
        "__EDITOR_LINKS_HIDDEN_ATTR__": "" if editor_work_id else "hidden",
        "__EDITOR_WORK_HREF__": f"/works/{escape(editor_work_id)}",
        "__EDITOR_READER_HREF__": f"/reader/{escape(editor_work_id)}",
        "__EDITOR_MANAGER_HIDDEN_ATTR__": "" if editor_work_id else "hidden",
        "__EDITOR_PAGES_HTML__": _editor_pages_html(editor_work_id, pages),
        "__EDITOR_CHAPTERS_HTML__": _editor_chapters_html(editor_work_id, chapters),
        "__INGEST_STATUS__": escape(ingest_status),
        "__INGEST_STATUS_CLASS__": _status_class(ingest_status_kind),
        "__INGEST_STATUS_HIDDEN_ATTR__": "" if ingest_status else "hidden",
        "__META_TITLE__": escape(str(data.get("title", ""))),
        "__META_SUMMARY__": escape(str(data.get("summary", ""))),
        "__META_RATING_OPTIONS_HTML__": _options_html(
            RATING_CHOICES,
            str(data.get("rating", "Not Rated")),
        ),
        "__META_WARNINGS__": escape(_as_csv(data.get("warnings", ""))),
        "__META_LANGUAGE__": escape(str(data.get("language", "en"))),
        "__META_SERIES__": escape(str(data.get("series", ""))),
        "__META_SERIES_INDEX__": escape(str(data.get("series_index", ""))),
        "__META_PUBLISHED_AT__": escape(str(data.get("published_at", ""))),
        "__META_FANDOMS__": escape(_as_csv(data.get("fandoms", ""))),
        "__META_RELATIONSHIPS__": escape(_as_csv(data.get("relationships", ""))),
        "__META_CHARACTERS__": escape(_as_csv(data.get("characters", ""))),
        "__META_FREEFORM_TAGS__": escape(_as_csv(data.get("freeform_tags", ""))),
        "__STATUS_IN_PROGRESS_SELECTED__": "selected"
        if str(data.get("status", "in_progress")) == "in_progress"
        else "",
        "__STATUS_COMPLETE_SELECTED__": "selected"
        if str(data.get("status", "in_progress")) == "complete"
        else "",
        "__WARNINGS_OPTIONS_HTML__": _datalist_options_html("archive_warning"),
        "__FANDOM_OPTIONS_HTML__": _datalist_options_html("fandom"),
        "__RELATIONSHIP_OPTIONS_HTML__": _datalist_options_html("relationship"),
        "__CHARACTER_OPTIONS_HTML__": _datalist_options_html("character"),
        "__FREEFORM_OPTIONS_HTML__": _datalist_options_html("freeform"),
    }
    replacements.update(user_menu_replacements(request))

    if result_payload is not None:
        replacements["__INGEST_RESULT_HIDDEN_ATTR__"] = ""
        replacements["__INGEST_RESULT__"] = escape(
            json.dumps(result_payload, ensure_ascii=True, indent=2)
        )
    else:
        replacements["__INGEST_RESULT_HIDDEN_ATTR__"] = "hidden"
        replacements["__INGEST_RESULT__"] = ""

    for marker, value in replacements.items():
        ingest_html = ingest_html.replace(marker, value)

    response.status_code = 200
    response.content_type = "text/html; charset=utf-8"
    response.set_data(ingest_html)
    return response
