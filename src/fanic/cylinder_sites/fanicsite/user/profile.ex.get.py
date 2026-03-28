from collections.abc import Mapping
from collections.abc import Sequence
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.profile_shared import render_profile_shared_sections
from fanic.repository import can_view_work
from fanic.repository import get_user_theme_preference
from fanic.repository import list_fanart_items_by_uploader
from fanic.repository import list_recent_reading_history
from fanic.repository import list_user_bookmarks
from fanic.repository import list_work_comments
from fanic.repository import list_works_by_uploader
from fanic.repository import user_prefers_explicit
from fanic.repository import user_prefers_mature
from fanic.repository import work_kudos_count
from fanic.settings import get_settings


def _uploaded_works_html(works: list[dict[str, object]]) -> str:
    if not works:
        return '<p class="profile-meta">No uploaded works yet.</p>'

    items: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        title = escape(str(work.get("title", "Untitled")))
        page_count = escape(str(work.get("page_count", 0)))
        status = escape(str(work.get("status", "in_progress")))
        kudos_count = escape(str(work.get("kudos_count", 0)))
        comments_count = escape(str(work.get("comments_count", 0)))
        items.append(
            f'<li><a href="/works/{work_id}">{title}</a> '
            f'<span class="profile-meta">({status}, {page_count} pages, {kudos_count} kudos, {comments_count} comments)</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _recent_history_html(history_rows: Sequence[Mapping[str, object]]) -> str:
    if not history_rows:
        return '<p class="profile-meta">No reading history yet.</p>'

    items: list[str] = []
    for row in history_rows:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        page_index = escape(str(row.get("page_index", 1)))
        updated_at = escape(str(row.get("updated_at", "")))
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">(continue at page {page_index}; last viewed {updated_at})</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _bookmarks_html(bookmarks: Sequence[Mapping[str, object]]) -> str:
    if not bookmarks:
        return '<p class="profile-meta">No bookmarks yet.</p>'

    items: list[str] = []
    for row in bookmarks:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        author_username = escape(str(row.get("author_username", "unknown")))
        message = escape(str(row.get("message", "")))
        page_index = escape(str(row.get("page_index", 1)))

        message_html = f' <span class="profile-meta">- {message}</span>' if message else ""
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">by <a href="/users/{author_username}">{author_username}</a> (saved at page {page_index})</span>'
            f"{message_html}</li>"
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _fanart_html(uploader_username: str, fanart_items: Sequence[Mapping[str, object]]) -> str:
    if not fanart_items:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    _ = uploader_username
    items: list[str] = []
    for row in fanart_items:
        title = escape(str(row.get("title", "Untitled")))
        image_name = escape(str(row.get("image_filename", "")))
        items.append(f'<li><a href="/fanart/images/{image_name}">{title}</a></li>')
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/profile":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    save_msg = request.args.get("msg", "").strip()
    pref_status_text = "Preference saved." if save_msg == "saved" else ""
    pref_status_class = "success" if save_msg == "saved" else ""
    pref_status_hidden = "" if save_msg == "saved" else "hidden"

    theme_status_text = ""
    theme_status_class = ""
    theme_status_hidden = "hidden"
    if save_msg == "theme_saved":
        theme_status_text = "Theme preferences saved."
        theme_status_class = "success"
        theme_status_hidden = ""
    elif save_msg == "theme_parse_error":
        theme_status_text = "Invalid theme.toml format."
        theme_status_class = "error"
        theme_status_hidden = ""
    elif save_msg == "theme_upload_error":
        theme_status_text = "Failed to read uploaded theme.toml file."
        theme_status_class = "error"
        theme_status_hidden = ""

    if username is None:
        shared_sections_html = render_profile_shared_sections(
            {
                "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "hidden",
                "__PROFILE_UPLOADED_WORKS_HTML__": "",
                "__PROFILE_FANART_HIDDEN_ATTR__": "hidden",
                "__PROFILE_FANART_HTML__": "",
                "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "hidden",
                "__PROFILE_BOOKMARKS_HTML__": "",
            }
        )
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_SUBTITLE_HIDDEN_ATTR__": "",
            "__PROFILE_STATUS__": "Not logged in.",
            "__PROFILE_STATUS_CLASS__": "error",
            "__PROFILE_STATUS_HIDDEN_ATTR__": "",
            "__PROFILE_DETAILS__": 'Use <a href="/account/login">Login</a> to sign in.',
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": "hidden",
            "__PROFILE_PUBLIC_HREF__": "",
            "__PROFILE_SETTINGS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_PREFS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_VIEW_MATURE_CHECKED_ATTR__": "",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": "",
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
            "__PROFILE_CUSTOM_THEME_ENABLED_CHECKED_ATTR__": "",
            "__PROFILE_THEME_STATUS__": theme_status_text,
            "__PROFILE_THEME_STATUS_CLASS__": theme_status_class,
            "__PROFILE_THEME_STATUS_HIDDEN_ATTR__": theme_status_hidden,
            "__PROFILE_HISTORY_HIDDEN_ATTR__": "hidden",
            "__PROFILE_HISTORY_LIMIT__": "0",
            "__PROFILE_HISTORY_HTML__": "",
            "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
        }
    else:
        history_limit = get_settings().profile_history_limit
        recent_history = list_recent_reading_history(username, limit=history_limit)
        uploaded_works_raw = list_works_by_uploader(username)
        uploaded_works: list[dict[str, object]] = []
        for work in uploaded_works_raw:
            work_id = str(work.get("id", "")).strip()
            work_with_counts: dict[str, object] = dict(work)
            if work_id:
                work_with_counts["kudos_count"] = work_kudos_count(work_id)
                work_with_counts["comments_count"] = len(list_work_comments(work_id))
            else:
                work_with_counts["kudos_count"] = 0
                work_with_counts["comments_count"] = 0
            uploaded_works.append(work_with_counts)
        raw_bookmarks = list_user_bookmarks(username)
        fanart_items = list_fanart_items_by_uploader(username, limit=30)
        visible_bookmarks = [
            row for row in raw_bookmarks if can_view_work(username, {"rating": row.get("rating", "Not Rated")})
        ]
        shared_sections_html = render_profile_shared_sections(
            {
                "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "",
                "__PROFILE_UPLOADED_WORKS_HTML__": _uploaded_works_html(uploaded_works),
                "__PROFILE_FANART_HIDDEN_ATTR__": "",
                "__PROFILE_FANART_HTML__": _fanart_html(username, fanart_items),
                "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "",
                "__PROFILE_BOOKMARKS_HTML__": _bookmarks_html(visible_bookmarks),
            }
        )
        view_mature_checked = "checked" if user_prefers_mature(username) else ""
        view_explicit_checked = "checked" if user_prefers_explicit(username) else ""
        theme_preference = get_user_theme_preference(username)
        custom_theme_checked = "checked" if theme_preference["enabled"] else ""
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_SUBTITLE_HIDDEN_ATTR__": "",
            "__PROFILE_STATUS__": "Logged in.",
            "__PROFILE_STATUS_CLASS__": "",
            "__PROFILE_STATUS_HIDDEN_ATTR__": "",
            "__PROFILE_DETAILS__": f"Username: {escape(username)}",
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": "",
            "__PROFILE_PUBLIC_HREF__": f"/users/{escape(username)}",
            "__PROFILE_SETTINGS_HIDDEN_ATTR__": "",
            "__PROFILE_PREFS_HIDDEN_ATTR__": "",
            "__PROFILE_VIEW_MATURE_CHECKED_ATTR__": view_mature_checked,
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": view_explicit_checked,
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
            "__PROFILE_CUSTOM_THEME_ENABLED_CHECKED_ATTR__": custom_theme_checked,
            "__PROFILE_THEME_STATUS__": theme_status_text,
            "__PROFILE_THEME_STATUS_CLASS__": theme_status_class,
            "__PROFILE_THEME_STATUS_HIDDEN_ATTR__": theme_status_hidden,
            "__PROFILE_HISTORY_HIDDEN_ATTR__": "",
            "__PROFILE_HISTORY_LIMIT__": escape(str(history_limit)),
            "__PROFILE_HISTORY_HTML__": _recent_history_html(recent_history),
            "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
        }

    return render_html_template(request, response, "profile.html", replacements)
