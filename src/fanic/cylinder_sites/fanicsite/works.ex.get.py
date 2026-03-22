from __future__ import annotations

from html import escape
from urllib.parse import quote

from fanic.cylinder_sites.common import ADMIN_USERNAME
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import rating_badge_html
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.editor_gallery import render_editor_chapters_html
from fanic.cylinder_sites.editor_gallery import render_editor_page_gallery_html
from fanic.cylinder_sites.editor_metadata import RATING_CHOICES
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.editor_metadata import render_options_html
from fanic.cylinder_sites.editor_metadata import selected_attr
from fanic.repository import can_view_work
from fanic.repository import get_work
from fanic.repository import get_work_version_manifest
from fanic.repository import has_user_kudoed_work
from fanic.repository import list_work_chapters
from fanic.repository import list_work_comments
from fanic.repository import list_work_page_rows
from fanic.repository import list_work_versions
from fanic.repository import work_kudos_count


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


def _work_versions_list_html(work_id: str, selected_version_id: str) -> str:
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
        selected_attr = (
            ' aria-current="page"' if version_id == selected_version_id else ""
        )
        version_href = f"/works/{escape(work_id)}/versions/{quote(version_id)}"
        items.append(
            "<li>"
            + f'<a href="{version_href}"{selected_attr}>{created_at}</a>'
            + f' <span class="profile-meta">({action} | {actor if actor else "unknown"} | {page_count} pages)</span>'
            + "</li>"
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _version_metadata_html(version_manifest: dict[str, object]) -> str:
    work_block = version_manifest.get("work")
    if not isinstance(work_block, dict):
        work_block = {}

    rows = [
        ("Version ID", escape(str(version_manifest.get("version_id", "")))),
        ("Created", escape(str(version_manifest.get("created_at", "")))),
        ("Action", escape(str(version_manifest.get("action", "")))),
        (
            "Actor",
            escape(
                str(
                    version_manifest.get("actor", "")
                    if version_manifest.get("actor", "")
                    else "unknown"
                )
            ),
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

        uploader = str(
            work.get("uploader_username") if work.get("uploader_username") else ""
        )
        if not _can_edit_work(username, uploader):
            return text_error(response, "Forbidden", 403)

        tags = work.get("tags", [])
        warnings_tags = _tag_names_csv(tags, "archive_warning")
        warnings_text = (
            warnings_tags if warnings_tags else str(work.get("warnings", ""))
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
            "page-add-too-large",
            "page-add-unsupported-extension",
            "page-add-unsupported-content-type",
            "page-add-rate-limited",
            "page-add-busy",
            "page-replace-failed",
            "page-replace-too-large",
            "page-replace-unsupported-extension",
            "page-replace-unsupported-content-type",
            "page-replace-rate-limited",
            "page-replace-busy",
            "page-delete-failed",
            "page-move-failed",
            "page-reorder-failed",
            "chapter-add-failed",
            "chapter-update-failed",
            "chapter-delete-failed",
        }:
            if save_msg in {"page-add-too-large", "page-replace-too-large"}:
                status_text = (
                    "Upload rejected: file is larger than the configured limit."
                )
            elif save_msg in {
                "page-add-unsupported-extension",
                "page-replace-unsupported-extension",
            }:
                status_text = "Upload rejected: file extension is not allowed."
            elif save_msg in {
                "page-add-unsupported-content-type",
                "page-replace-unsupported-content-type",
            }:
                status_text = "Upload rejected: content type is not allowed."
            elif save_msg in {"page-add-rate-limited", "page-replace-rate-limited"}:
                status_text = "Upload rate limit reached. Please wait and try again."
            elif save_msg in {"page-add-busy", "page-replace-busy"}:
                status_text = "Too many active uploads. Please retry shortly."
            else:
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
                "__EDIT_RATING_OPTIONS_HTML__": render_options_html(
                    RATING_CHOICES,
                    str(work.get("rating", "Not Rated")),
                ),
                "__EDIT_WARNINGS__": escape(warnings_text),
                "__EDIT_LANGUAGE__": escape(str(work.get("language", "en"))),
                "__EDIT_SERIES__": escape(
                    str(
                        work.get("series_name", "")
                        if work.get("series_name", "")
                        else ""
                    )
                ),
                "__EDIT_SERIES_INDEX__": escape(
                    str(
                        work.get("series_index", "")
                        if work.get("series_index", "")
                        else ""
                    )
                ),
                "__EDIT_PUBLISHED_AT__": escape(
                    str(
                        work.get("published_at", "")
                        if work.get("published_at", "")
                        else ""
                    )
                ),
                "__EDIT_FANDOMS__": escape(_tag_names_csv(tags, "fandom")),
                "__EDIT_RELATIONSHIPS__": escape(_tag_names_csv(tags, "relationship")),
                "__EDIT_CHARACTERS__": escape(_tag_names_csv(tags, "character")),
                "__EDIT_FREEFORM_TAGS__": escape(_tag_names_csv(tags, "freeform")),
                "__STATUS_IN_PROGRESS_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "in_progress"
                ),
                "__STATUS_COMPLETE_SELECTED__": selected_attr(
                    str(work.get("status", "in_progress")), "complete"
                ),
                "__EDIT_STATUS_TEXT__": status_text,
                "__EDIT_STATUS_CLASS__": status_class,
                "__EDIT_STATUS_HIDDEN_ATTR__": status_hidden,
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
                    pages,
                    chapters,
                ),
                "__EDITOR_CHAPTERS_HTML__": render_editor_chapters_html(
                    work_id,
                    chapters,
                    form_action=f"/works/{work_id}/edit",
                    action_field_name="edit_action",
                    update_action_value="editor-update-chapter",
                    delete_action_value="editor-delete-chapter",
                    delete_confirm_message="Delete this chapter?",
                ),
                **render_common_tag_datalist_replacements(),
            },
        )

    if len(tail) in {2, 3} and tail[1] == "versions":
        work_id = tail[0]
        work = get_work(work_id)
        if not work:
            return text_error(response, "Work not found", 404)

        username = current_user(request)
        if not can_view_work(username, work):
            return text_error(response, "Work not found", 404)

        versions = list_work_versions(work_id, limit=50)
        if not versions:
            return render_html_template(
                request,
                response,
                "work-versions.html",
                {
                    "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                    "__WORK_HREF__": f"/works/{escape(work_id)}",
                    "__WORK_READER_HREF__": f"/reader/{escape(work_id)}",
                    "__WORK_VERSIONS_LIST_HTML__": '<p class="profile-meta">No versions recorded yet.</p>',
                    "__VERSION_STATUS__": "No versions recorded yet.",
                    "__VERSION_STATUS_CLASS__": "",
                    "__VERSION_READER_HREF__": f"/reader/{escape(work_id)}",
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

        quoted_version = quote(selected_version_id)
        return render_html_template(
            request,
            response,
            "work-versions.html",
            {
                "__WORK_TITLE__": escape(str(work.get("title", "Untitled"))),
                "__WORK_HREF__": f"/works/{escape(work_id)}",
                "__WORK_READER_HREF__": f"/reader/{escape(work_id)}",
                "__WORK_VERSIONS_LIST_HTML__": _work_versions_list_html(
                    work_id,
                    selected_version_id,
                ),
                "__VERSION_STATUS__": escape(f"Viewing version {selected_version_id}"),
                "__VERSION_STATUS_CLASS__": "success",
                "__VERSION_READER_HREF__": f"/reader/{escape(work_id)}?version_id={quoted_version}",
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

    uploader = str(
        work.get("uploader_username") if work.get("uploader_username") else ""
    )
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
            "__WORK_VERSIONS_HREF__": f"/works/{escape(work_id)}/versions",
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
