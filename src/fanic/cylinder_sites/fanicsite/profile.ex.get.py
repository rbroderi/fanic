from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    render_html_template,
    text_error,
)
from fanic.repository import list_works_by_uploader, user_prefers_explicit


def _uploaded_works_html(works: list[dict[str, object]]) -> str:
    if not works:
        return '<p class="profile-meta">No uploaded works yet.</p>'

    items: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        title = escape(str(work.get("title", "Untitled")))
        page_count = escape(str(work.get("page_count", 0)))
        status = escape(str(work.get("status", "in_progress")))
        items.append(
            f'<li><a href="/works/{work_id}">{title}</a> '
            f'<span class="profile-meta">({status}, {page_count} pages)</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/profile":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    save_msg = request.args.get("msg", "").strip()
    pref_status_text = "Preference saved." if save_msg == "saved" else ""
    pref_status_class = "success" if save_msg == "saved" else ""
    pref_status_hidden = "" if save_msg == "saved" else "hidden"

    if username is None:
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_STATUS__": "Not logged in.",
            "__PROFILE_STATUS_CLASS__": "error",
            "__PROFILE_DETAILS__": 'Use <a href="/login">Login</a> to sign in.',
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": "hidden",
            "__PROFILE_PUBLIC_HREF__": "",
            "__PROFILE_PREFS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": "",
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
            "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "hidden",
            "__PROFILE_UPLOADED_WORKS_HTML__": "",
        }
    else:
        uploaded_works = list_works_by_uploader(username)
        view_explicit_checked = "checked" if user_prefers_explicit(username) else ""
        replacements = {
            "__PROFILE_PAGE_TITLE__": "FANIC Profile",
            "__PROFILE_CARD_TITLE__": "Your Profile",
            "__PROFILE_CARD_SUBTITLE__": "This page shows your current FANIC session state.",
            "__PROFILE_STATUS__": "Logged in.",
            "__PROFILE_STATUS_CLASS__": "",
            "__PROFILE_DETAILS__": f"Username: {escape(username)}",
            "__PROFILE_PUBLIC_LINK_HIDDEN_ATTR__": "",
            "__PROFILE_PUBLIC_HREF__": f"/users/{escape(username)}",
            "__PROFILE_PREFS_HIDDEN_ATTR__": "",
            "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": view_explicit_checked,
            "__PROFILE_PREF_STATUS__": pref_status_text,
            "__PROFILE_PREF_STATUS_CLASS__": pref_status_class,
            "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": pref_status_hidden,
            "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "",
            "__PROFILE_UPLOADED_WORKS_HTML__": _uploaded_works_html(uploaded_works),
        }

    return render_html_template(request, response, "profile.html", replacements)
