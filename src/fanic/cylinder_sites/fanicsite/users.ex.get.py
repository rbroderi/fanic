from __future__ import annotations

from collections.abc import Sequence
from html import escape

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    render_html_template,
    route_tail,
    text_error,
)
from fanic.repository import WorkListItem, can_view_work, list_works_by_uploader


def _uploaded_works_html(works: Sequence[WorkListItem]) -> str:
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
            + f'<span class="profile-meta">({status}, {page_count} pages)</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["users"])
    if tail is None or len(tail) != 1:
        return text_error(response, "Not found", 404)

    profile_username = tail[0].strip()
    if not profile_username:
        return text_error(response, "Not found", 404)

    viewer = current_user(request)
    uploaded = [
        work
        for work in list_works_by_uploader(profile_username)
        if can_view_work(viewer, work)
    ]

    replacements = {
        "__PROFILE_PAGE_TITLE__": f"FANIC Profile - {escape(profile_username)}",
        "__PROFILE_CARD_TITLE__": f"{escape(profile_username)}'s Profile",
        "__PROFILE_CARD_SUBTITLE__": "Public profile and uploaded works.",
        "__PROFILE_STATUS__": "Public profile",
        "__PROFILE_STATUS_CLASS__": "",
        "__PROFILE_DETAILS__": f"Username: {escape(profile_username)}",
        "__PROFILE_PREFS_HIDDEN_ATTR__": "hidden",
        "__PROFILE_VIEW_EXPLICIT_CHECKED_ATTR__": "",
        "__PROFILE_PREF_STATUS__": "",
        "__PROFILE_PREF_STATUS_CLASS__": "",
        "__PROFILE_PREF_STATUS_HIDDEN_ATTR__": "hidden",
        "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "",
        "__PROFILE_UPLOADED_WORKS_HTML__": _uploaded_works_html(uploaded),
    }

    return render_html_template(request, response, "profile.html", replacements)
