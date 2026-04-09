from collections.abc import Mapping
from collections.abc import Sequence
from html import escape
from typing import Any
from typing import cast
from urllib.parse import quote

from fanic.cylinder_sites.common.protocols import StatusReplacements
from fanic.cylinder_sites.common.protocols import status_for_message
from fanic.cylinder_sites.common.protocols import status_visible
from fanic.repository.users import get_local_user
from fanic.repository.works import list_work_versions


def can_edit_work(username: str | None, uploader_username: str, *, is_admin: bool) -> bool:
    return bool(username) and (username == uploader_username or is_admin)


def tag_names_csv(tags: object, tag_type: str) -> str:
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


def comment_cards_html(comments: Sequence[Mapping[str, object]]) -> str:
    if not comments:
        return '<p class="profile-meta">No comments yet.</p>'

    parts: list[str] = []
    for comment in comments:
        username_raw = str(comment.get("username", "anon")).strip()
        display_name_raw = str(comment.get("commenter_display_name", "")).strip()
        display_name = display_name_raw if display_name_raw else username_raw
        commenter_href = f"/users/{quote(display_name, safe='')}"
        commenter_html = f'<a href="{commenter_href}">{escape(display_name)}</a>'
        created_at = escape(str(comment.get("created_at", "")))
        chapter_number = comment.get("chapter_number")
        if chapter_number is None:
            scope = "Overall"
        else:
            scope = f"Chapter {escape(str(chapter_number))}"
        body = escape(str(comment.get("body", ""))).replace("\n", "<br />")
        parts.append(
            f'<article class="card comment-card"><p class="comment-meta"><strong>{scope}</strong> by {commenter_html} on {created_at}</p><p>{body}</p></article>'
        )
    return "".join(parts)


def display_name_for_username(
    username: str,
    *,
    cache: dict[str, str],
) -> str:
    normalized_username = username.strip()
    if not normalized_username:
        return ""
    cached = cache.get(normalized_username)
    if cached is not None:
        return cached

    try:
        local_user = get_local_user(normalized_username)
    except Exception:
        cache[normalized_username] = normalized_username
        return normalized_username

    if local_user is None:
        cache[normalized_username] = normalized_username
        return normalized_username

    display_name = str(local_user.get("display_name", "")).strip()
    resolved = display_name if display_name else normalized_username
    cache[normalized_username] = resolved
    return resolved


def work_versions_list_html(
    work_id: str,
    selected_version_id: str,
    *,
    back_href: str,
) -> str:
    versions = list_work_versions(work_id, limit=30)
    if not versions:
        return '<p class="profile-meta">No versions recorded yet.</p>'

    actor_display_name_cache: dict[str, str] = {}
    items: list[str] = []
    for version in versions:
        version_id = escape(str(version.get("version_id", "")))
        created_at = escape(str(version.get("created_at", "")))
        action = escape(str(version.get("action", "")))
        actor_username = str(version.get("actor", "")).strip()
        actor_display_name_raw = str(version.get("actor_display_name", "")).strip()
        actor_display_name = (
            actor_display_name_raw
            if actor_display_name_raw
            else display_name_for_username(
                actor_username,
                cache=actor_display_name_cache,
            )
        )
        actor = escape(actor_display_name)
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


def version_metadata_html(version_manifest: dict[str, object]) -> str:
    work_block: object | dict[str, Any] | None = version_manifest.get("work")
    if not isinstance(work_block, dict):
        work_block = {}

    work_block = cast(dict[str, Any], work_block)
    actor_username = str(version_manifest.get("actor", "")).strip()
    actor_display_name = display_name_for_username(actor_username, cache={})
    rows = [
        ("Version ID", escape(str(version_manifest.get("version_id", "")))),
        ("Created", escape(str(version_manifest.get("created_at", "")))),
        ("Action", escape(str(version_manifest.get("action", "")))),
        (
            "Actor",
            escape(actor_display_name if actor_display_name else "unknown"),
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


def status_for_edit_message(save_msg: str) -> StatusReplacements:
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
            text = "Only admins can lower Explicit, and non-admins can only raise to Explicit from Mature."
            css_class = "error"
            hidden_attr = ""
        case _:
            text = ""
            css_class = ""
            hidden_attr = "hidden"
    return StatusReplacements(text, css_class, hidden_attr)


def status_for_work_message(msg: str) -> StatusReplacements:
    return status_for_message(
        msg,
        {
            "comment-saved": status_visible("Comment posted.", "success"),
            "kudos-saved": status_visible("Kudos sent.", "success"),
            "already-kudoed": status_visible("You already left kudos for this work.", ""),
            "login-required": status_visible("Login required to leave comments or kudos.", "error"),
            "comment-empty": status_visible("Comment cannot be empty.", "error"),
            "chapter-invalid": status_visible("Chapter number must be between 1 and page count.", "error"),
        },
    )
