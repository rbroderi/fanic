from __future__ import annotations

from collections.abc import Sequence
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.profile_shared import render_profile_shared_sections
from fanic.repository import UserBookmarkRow
from fanic.repository import WorkListItem
from fanic.repository import can_view_work
from fanic.repository import list_user_bookmarks
from fanic.repository import list_works_by_uploader


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


def _bookmarks_html(bookmarks: list[UserBookmarkRow]) -> str:
    if not bookmarks:
        return '<p class="profile-meta">No bookmarks yet.</p>'

    items: list[str] = []
    for row in bookmarks:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        author_username = escape(str(row.get("author_username", "unknown")))
        message = escape(str(row.get("message", "")))
        page_index = escape(str(row.get("page_index", 1)))
        message_html = (
            f' <span class="profile-meta">- {message}</span>' if message else ""
        )
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">by <a href="/users/{author_username}">{author_username}</a> (saved at page {page_index})</span>'
            f"{message_html}</li>"
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
    raw_bookmarks = list_user_bookmarks(profile_username)
    visible_bookmarks = [
        row
        for row in raw_bookmarks
        if can_view_work(viewer, {"rating": row.get("rating", "Not Rated")})
    ]
    shared_sections_html = render_profile_shared_sections(
        {
            "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "",
            "__PROFILE_UPLOADED_WORKS_HTML__": _uploaded_works_html(uploaded),
            "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "",
            "__PROFILE_BOOKMARKS_HTML__": _bookmarks_html(visible_bookmarks),
        }
    )

    replacements = {
        "__PROFILE_PAGE_TITLE__": f"FANIC Profile - {escape(profile_username)}",
        "__PROFILE_CARD_TITLE__": f"{escape(profile_username)}'s Profile",
        "__PROFILE_CARD_SUBTITLE__": "Public profile and uploaded works.",
        "__PROFILE_DETAILS__": f"Username: {escape(profile_username)}",
        "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
    }

    return render_html_template(request, response, "profile-public.html", replacements)

