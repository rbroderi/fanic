from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from urllib.parse import quote
from urllib.parse import urlencode

if TYPE_CHECKING:
    from _typeshed import ConvertibleToInt
else:
    type ConvertibleToInt = int | str | bytes

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import media_url
from fanic.cylinder_sites.common import rating_badge_html
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.editor_gallery import render_editor_chapters_html
from fanic.cylinder_sites.editor_gallery import render_editor_page_gallery_html
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.editor_metadata import selected_attr
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.repository import can_view_work
from fanic.repository import get_page_files
from fanic.repository import get_work
from fanic.repository import get_work_version_manifest
from fanic.repository import has_user_kudoed_work
from fanic.repository import list_work_chapters
from fanic.repository import list_work_comments
from fanic.repository import list_work_page_rows
from fanic.repository import list_work_versions
from fanic.repository import load_progress
from fanic.repository import work_kudos_count


@dataclass(frozen=True, slots=True)
class StatusMessage:
    text: str
    css_class: str
    hidden_attr: str


def _can_edit_work(username: str | None, uploader_username: str, *, is_admin: bool) -> bool:
    return bool(username) and (username == uploader_username or is_admin)


def _tag_names_csv(tags: object, tag_type: str) -> str:
    if not isinstance(tags, list):
        return ""
    names: list[str] = []
    for tag in cast(list[Any], tags):
        if not isinstance(tag, dict):
            continue
        tag = cast(dict[str, Any], tag)
        if str(tag.get("type", "")) != tag_type:
            continue
        name = str(tag.get("name", "")).strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _comment_cards_html(comments: Sequence[Mapping[str, object]]) -> str:
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


def _work_versions_list_html(
    work_id: str,
    selected_version_id: str,
    *,
    back_href: str,
) -> str:
    versions = list_work_versions(work_id, limit=30)
    if not versions:
        return '<p class="profile-meta">No versions recorded yet.</p>'

    items: list[str] = []
    for version in versions:
        version_id = escape(str(version.get("version_id", "")))
        created_at = escape(str(version.get("created_at", "")))
        action = escape(str(version.get("action", "")))
        actor = escape(str(version.get("actor", "")))
        page_count = escape(str(version.get("page_count", 0)))
        selected_attr = ' aria-current="page"' if version_id == selected_version_id else ""
        version_href = f"/comic/{escape(work_id)}/versions/{quote(version_id)}"
        if back_href:
            version_href += f"?back={quote(back_href, safe='')}"
        items.append(
            "<li>"
            + f'<a href="{version_href}"{selected_attr}>{created_at}</a>'
            + f' <span class="profile-meta">({action} | {actor if actor else "unknown"} | {page_count} pages)</span>'
            + "</li>"
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _version_metadata_html(version_manifest: dict[str, object]) -> str:
    work_block: object | dict[str, Any] | None = version_manifest.get("work")
    if not isinstance(work_block, dict):
        work_block = {}

    work_block = cast(dict[str, Any], work_block)
    rows = [
        ("Version ID", escape(str(version_manifest.get("version_id", "")))),
        ("Created", escape(str(version_manifest.get("created_at", "")))),
        ("Action", escape(str(version_manifest.get("action", "")))),
        (
            "Actor",
            escape(str(version_manifest.get("actor", "") if version_manifest.get("actor", "") else "unknown")),
        ),
        ("Title", escape(str(work_block.get("title", "Untitled")))),
        ("Rating", escape(str(work_block.get("rating", "Not Rated")))),
        ("Status", escape(str(work_block.get("status", "in_progress")))),
        ("Page Count", escape(str(work_block.get("page_count", 0)))),
        ("Updated At", escape(str(work_block.get("updated_at", "")))),
    ]
    parts = ["<dl>"]
    for label, value in rows:
        parts.append(f"<dt><strong>{label}</strong></dt><dd>{value}</dd>")
    parts.append("</dl>")
    return "".join(parts)


def _status_for_edit_message(save_msg: str) -> StatusMessage:
    text = ""
    css_class = ""
    hidden_attr = "hidden"
    match save_msg:
        case "saved":
            text = "Metadata saved."
            css_class = "success"
            hidden_attr = ""
        case "page-added":
            text = "Page uploaded."
            css_class = "success"
            hidden_attr = ""
        case "page-added-rating-elevated":
            text = "Page uploaded. Rating auto-elevated based on moderation detection."
            css_class = "success"
            hidden_attr = ""
        case "page-replaced":
            text = "Page replaced."
            css_class = "success"
            hidden_attr = ""
        case "page-replaced-rating-elevated":
            text = "Page replaced. Rating auto-elevated based on moderation detection."
            css_class = "success"
            hidden_attr = ""
        case "page-deleted":
            text = "Page deleted."
            css_class = "success"
            hidden_attr = ""
        case "page-moved":
            text = "Page moved."
            css_class = "success"
            hidden_attr = ""
        case "page-reordered":
            text = "Gallery order saved. Page order and chapter assignments updated."
            css_class = "success"
            hidden_attr = ""
        case "chapter-added":
            text = "Chapter added."
            css_class = "success"
            hidden_attr = ""
        case "chapter-updated":
            text = "Chapter updated."
            css_class = "success"
            hidden_attr = ""
        case "chapter-deleted":
            text = "Chapter deleted."
            css_class = "success"
            hidden_attr = ""
        case (
            "page-file-required"
            | "page-add-failed"
            | "page-add-too-large"
            | "page-add-unsupported-extension"
            | "page-add-unsupported-content-type"
            | "page-add-rate-limited"
            | "page-add-busy"
            | "page-replace-failed"
            | "page-replace-too-large"
            | "page-replace-unsupported-extension"
            | "page-replace-unsupported-content-type"
            | "page-replace-rate-limited"
            | "page-replace-busy"
            | "page-delete-failed"
            | "page-move-failed"
            | "page-reorder-failed"
            | "chapter-add-failed"
            | "chapter-update-failed"
            | "chapter-delete-failed"
        ):
            css_class = "error"
            hidden_attr = ""
            match save_msg:
                case "page-add-too-large" | "page-replace-too-large":
                    text = "Upload rejected: file is larger than the configured limit."
                case "page-add-unsupported-extension" | "page-replace-unsupported-extension":
                    text = "Upload rejected: file extension is not allowed."
                case "page-add-unsupported-content-type" | "page-replace-unsupported-content-type":
                    text = "Upload rejected: content type is not allowed."
                case "page-add-rate-limited" | "page-replace-rate-limited":
                    text = "Upload rate limit reached. Please wait and try again."
                case "page-add-busy" | "page-replace-busy":
                    text = "Too many active uploads. Please retry shortly."
                case _:
                    text = "Edit action failed. Check inputs and permissions."
        case "page-blocked":
            text = "Upload blocked by moderation policy (photorealistic images are not allowed)."
            css_class = "error"
            hidden_attr = ""
        case "explicit-rating-locked":
            text = "Only admins can lower a work from Explicit to a lower rating."
            css_class = "error"
            hidden_attr = ""
        case _:
            text = ""
            css_class = ""
            hidden_attr = "hidden"
    return StatusMessage(text, css_class, hidden_attr)


def _status_for_work_message(msg: str) -> StatusMessage:
    text = ""
    css_class = ""
    hidden_attr = ""
    match msg:
        case "comment-saved":
            text = "Comment posted."
            css_class = "success"
            hidden_attr = ""
        case "kudos-saved":
            text = "Kudos sent."
            css_class = "success"
            hidden_attr = ""
        case "already-kudoed":
            text = "You already left kudos for this work."
            css_class = ""
            hidden_attr = ""
        case "login-required":
            text = "Login required to leave comments or kudos."
            css_class = "error"
            hidden_attr = ""
        case "comment-empty":
            text = "Comment cannot be empty."
            css_class = "error"
            hidden_attr = ""
        case "chapter-invalid":
            text = "Chapter number must be between 1 and page count."
            css_class = "error"
            hidden_attr = ""
        case _:
            text = ""
            css_class = ""
            hidden_attr = "hidden"
    return StatusMessage(text, css_class, hidden_attr)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["comic"])
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

        uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
        user_role = role_for_user(username)
        if not _can_edit_work(
            username,
            uploader,
            is_admin=user_role in {"superadmin", "admin"},
        ):
            return text_error(response, "Forbidden", 403)

        tags = work.get("tags", [])
        warnings_tags = _tag_names_csv(tags, "archive_warning")
        warnings_text = warnings_tags if warnings_tags else str(work.get("warnings", ""))

        save_msg = request.args.get("msg", "").strip()
        edit_status = _status_for_edit_message(save_msg)

        pages = cast(list[dict[str, Any]], list_work_page_rows(work_id))
        chapters = cast(list[dict[str, Any]], list_work_chapters(work_id))
        # Normalize TypedDict rows to plain dict rows for editor helper signatures.
        gallery_pages: list[dict[str, ConvertibleToInt]] = []
        for page in pages:
            page_index_obj = page.get("page_index")
            if page_index_obj is None:
                page_index_obj = page.get("page_number", 0)
            image_filename_obj = page.get("image_filename")
            if image_filename_obj is None:
                image_filename_obj = page.get("filename", "")
            gallery_pages.append(
                {
                    "page_index": int(page_index_obj),
                    "image_filename": str(image_filename_obj),
                }
            )

        gallery_chapters: list[dict[str, ConvertibleToInt]] = []
        for chapter in chapters:
            chapter_index_obj = chapter.get("chapter_index")
            if chapter_index_obj is None:
                chapter_index_obj = chapter.get("number", 0)
            gallery_chapters.append(
                {
                    "id": int(chapter.get("id", 0)),
                    "chapter_index": int(chapter_index_obj),
                    "title": str(chapter.get("title", "Untitled Chapter")),
                    "start_page": int(chapter.get("start_page", 1)),
                    "end_page": int(chapter.get("end_page", 1)),
                }
            )

        return render_html_template(
            request,
            response,
            "work-edit.html",
            {
                "__WORK_ID__": escape(work_id),
                "__EDIT_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDIT_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDIT_RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDIT_WARNINGS__": escape(warnings_text),
                "__EDIT_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDIT_SERIES__": escape(str(work.get("series_name", "") if work.get("series_name", "") else "")),
                "__EDIT_SERIES_INDEX__": escape(
                    str(work.get("series_index", "") if work.get("series_index", "") else "")
                ),
                "__EDIT_PUBLISHED_AT__": escape(
                    str(work.get("published_at", "") if work.get("published_at", "") else "")
                ),
                "__EDIT_FANDOMS__": escape(_tag_names_csv(tags, "fandom")),
                "__EDIT_RELATIONSHIPS__": escape(_tag_names_csv(tags, "relationship")),
                "__EDIT_CHARACTERS__": escape(_tag_names_csv(tags, "character")),
                "__EDIT_FREEFORM_TAGS__": escape(_tag_names_csv(tags, "freeform")),
                "__STATUS_IN_PROGRESS_SELECTED__": selected_attr(str(work.get("status", "in_progress")), "in_progress"),
                "__STATUS_COMPLETE_SELECTED__": selected_attr(str(work.get("status", "in_progress")), "complete"),
                "__EDIT_STATUS_TEXT__": edit_status.text,
                "__EDIT_STATUS_CLASS__": edit_status.css_class,
                "__EDIT_STATUS_HIDDEN_ATTR__": edit_status.hidden_attr,
                "__EDITOR_WORK_ID__": escape(work_id),
                "__EDITOR_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__EDITOR_SUMMARY__": escape(str(work.get("summary", ""))),
                "__EDITOR_RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDITOR_STATUS_IN_PROGRESS_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "in_progress"
                ),
                "__EDITOR_STATUS_COMPLETE_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "complete"
                ),
                "__EDITOR_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDITOR_PAGE_GALLERY_HTML__": render_editor_page_gallery_html(
                    work_id,
                    gallery_pages,
                    gallery_chapters,
                ),
                "__EDITOR_CHAPTERS_HTML__": render_editor_chapters_html(
                    work_id,
                    gallery_chapters,
                    form_action=f"/comic/{work_id}/edit",
                    action_field_name="edit_action",
                    update_action_value="editor-update-chapter",
                    delete_action_value="editor-delete-chapter",
                    delete_confirm_message="Delete this chapter?",
                ),
                **render_common_tag_datalist_replacements(),
            },
        )

    back_href = request.args.get("back", "").strip()

    if len(tail) in {2, 3} and tail[1] == "versions":
        work_id = tail[0]
        work = get_work(work_id)
        if not work:
            return text_error(response, "Work not found", 404)

        username = current_user(request)
        if not can_view_work(username, work):
            return text_error(response, "Work not found", 404)

        reader_query = {"back": back_href} if back_href else {}
        reader_query_string = urlencode(reader_query)
        reader_href = (
            f"/tools/reader/{escape(work_id)}?{reader_query_string}"
            if reader_query_string
            else f"/tools/reader/{escape(work_id)}"
        )
        versions = list_work_versions(work_id, limit=50)
        if not versions:
            work_href = f"/comic/{escape(work_id)}"
            if back_href:
                work_href += f"?back={quote(back_href, safe='')}"
            return render_html_template(
                request,
                response,
                "work-versions.html",
                {
                    "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                    "__WORK_HREF__": work_href,
                    "__WORK_READER_HREF__": reader_href,
                    "__WORK_VERSIONS_LIST_HTML__": '<p class="profile-meta">No versions recorded yet.</p>',
                    "__VERSION_STATUS__": "No versions recorded yet.",
                    "__VERSION_STATUS_CLASS__": "",
                    "__VERSION_READER_HREF__": reader_href,
                    "__VERSION_METADATA_HTML__": '<p class="profile-meta">No snapshot metadata available.</p>',
                },
            )

        selected_version_id = ""
        if len(tail) == 3:
            selected_version_id = tail[2]
        if not selected_version_id:
            selected_version_id = str(versions[0].get("version_id", ""))

        version_manifest = get_work_version_manifest(work_id, selected_version_id)
        if version_manifest is None:
            return text_error(response, "Version not found", 404)

        version_reader_query = {"version_id": selected_version_id}
        if back_href:
            version_reader_query["back"] = back_href
        version_reader_query_string = urlencode(version_reader_query)
        version_reader_href = f"/tools/reader/{escape(work_id)}?{version_reader_query_string}"
        work_href = f"/comic/{escape(work_id)}"
        if back_href:
            work_href += f"?back={quote(back_href, safe='')}"
        return render_html_template(
            request,
            response,
            "work-versions.html",
            {
                "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__WORK_HREF__": work_href,
                "__WORK_READER_HREF__": reader_href,
                "__WORK_VERSIONS_LIST_HTML__": _work_versions_list_html(
                    work_id,
                    selected_version_id,
                    back_href=back_href,
                ),
                "__VERSION_STATUS__": escape(f"Viewing version {selected_version_id}"),
                "__VERSION_STATUS_CLASS__": "success",
                "__VERSION_READER_HREF__": version_reader_href,
                "__VERSION_METADATA_HTML__": _version_metadata_html(version_manifest),
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
    summary_raw = str(work.get("summary", ""))
    summary = escape(summary_raw if summary_raw else "No summary provided.")
    rating_html = rating_badge_html(work.get("rating", "Not Rated"))
    status = escape(str(work.get("status", "in_progress")))
    page_count = escape(str(work.get("page_count", 0)))
    cover_page_index_raw = work.get("cover_page_index", 1)
    cover_page_index = int(cover_page_index_raw) if cover_page_index_raw else 1
    cover_files = get_page_files(work_id, cover_page_index)
    cover_image_name = str(cover_files["image"]).strip() if cover_files else ""
    work_id_quoted = quote(work_id, safe="")
    if cover_image_name:
        cover_src = media_url(f"/comic/{work_id_quoted}/pages/{quote(cover_image_name, safe='/')}")
    else:
        cover_src = media_url("/static/logo.png")

    tags_obj = work.get("tags", [])
    tag_html = ""
    if isinstance(tags_obj, list):
        rendered_tags: list[str] = []
        for tag_obj in cast(list[Any], tags_obj):
            if isinstance(tag_obj, dict):
                tag = cast(dict[str, Any], tag_obj)
                tag_type = escape(str(tag.get("type", "tag")))
                tag_name = escape(str(tag.get("name", "")))
                rendered_tags.append(f'<span class="tag">{tag_type}: {tag_name}</span>')
        tag_html = "".join(rendered_tags)

    uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
    user_role = role_for_user(username)
    is_admin = user_role in {"superadmin", "admin"}
    can_edit = _can_edit_work(username, uploader, is_admin=is_admin)
    can_delete = is_admin
    comments = list_work_comments(work_id)
    kudos = work_kudos_count(work_id)
    has_kudoed = has_user_kudoed_work(work_id, username)
    progress_user_id = username if username else "anon"
    bookmark_page_index = load_progress(work_id, progress_user_id)

    msg = request.args.get("msg", "").strip()
    work_status = _status_for_work_message(msg)

    reader_query = {"back": back_href} if back_href else {}
    reader_query_string = urlencode(reader_query)
    reader_href = (
        f"/tools/reader/{escape(work_id)}?{reader_query_string}"
        if reader_query_string
        else f"/tools/reader/{escape(work_id)}"
    )
    versions_href = f"/comic/{escape(work_id)}/versions"
    if back_href:
        versions_href += f"?back={quote(back_href, safe='')}"

    return render_html_template(
        request,
        response,
        "work.html",
        {
            "__WORK_TITLE__": title,
            "__WORK_SUMMARY__": summary,
            "__WORK_META__": f"{rating_html} | {status} | {page_count} pages",
            "__WORK_COVER_SRC__": cover_src,
            "__WORK_READ_HREF__": reader_href,
            "__WORK_DOWNLOAD_HREF__": f"/api/comic/{escape(work_id)}/download",
            "__WORK_VERSIONS_HREF__": versions_href,
            "__WORK_TAGS_HTML__": tag_html,
            "__EDIT_METADATA_HREF__": f"/comic/{escape(work_id)}/edit",
            "__EDIT_METADATA_HIDDEN_ATTR__": "" if can_edit else "hidden",
            "__ADMIN_DELETE_HIDDEN_ATTR__": "" if can_delete else "hidden",
            "__WORK_ID__": escape(work_id),
            "__WORK_KUDOS_COUNT__": escape(str(kudos)),
            "__KUDOS_DISABLED_ATTR__": "disabled" if (not username or has_kudoed) else "",
            "__WORK_STATUS_TEXT__": work_status.text,
            "__WORK_STATUS_CLASS__": work_status.css_class,
            "__WORK_STATUS_HIDDEN_ATTR__": work_status.hidden_attr,
            "__COMMENTS_HTML__": _comment_cards_html(comments),
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html("copyright-dmca"),
            "__DMCA_WORK_ID__": escape(work_id),
            "__DMCA_WORK_TITLE__": title,
            "__DMCA_CLAIMED_URL__": f"/comic/{escape(work_id)}",
            "__WORK_BOOKMARK_WORK_ID__": escape(work_id),
            "__WORK_BOOKMARK_USER_ID__": escape(progress_user_id),
            "__WORK_BOOKMARK_PAGE_INDEX__": escape(str(bookmark_page_index)),
        },
    )
