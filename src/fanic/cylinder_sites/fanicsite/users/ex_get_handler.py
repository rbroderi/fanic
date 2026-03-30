from collections.abc import Sequence
from html import escape
from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.profile_shared import render_profile_shared_sections
from fanic.repository import FanartItemRow
from fanic.repository import UserBookmarkRow
from fanic.repository import WorkListItem
from fanic.repository import can_view_work
from fanic.repository import get_local_user
from fanic.repository import get_local_user_by_display_name
from fanic.repository import list_fanart_galleries_by_uploader
from fanic.repository import list_fanart_gallery_item_ids
from fanic.repository import list_fanart_items_by_uploader
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
            f'<li><a href="/comic/{work_id}">{title}</a> '
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
        author_username = str(row.get("author_username", "unknown"))
        author_display_name_raw = str(row.get("author_display_name", "")).strip()
        author_display_name = author_display_name_raw if author_display_name_raw else author_username
        author_profile_href = f"/users/{quote(author_display_name, safe='')}"
        message = escape(str(row.get("message", "")))
        page_index = escape(str(row.get("page_index", 1)))
        message_html = f' <span class="profile-meta">- {message}</span>' if message else ""
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">by <a href="{author_profile_href}">{escape(author_display_name)}</a> (saved at page {page_index})</span>'
            f"{message_html}</li>"
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"


def _fanart_html(
    uploader_username: str,
    uploader_profile_key: str,
    items: list[FanartItemRow],
) -> str:
    if not items:
        return '<p class="profile-meta">No fanart uploaded yet.</p>'

    gallery_slug_by_item_id: dict[str, str] = {}
    galleries = list_fanart_galleries_by_uploader(uploader_username)
    for gallery in galleries:
        gallery_id = str(gallery.get("id", "")).strip()
        gallery_slug = str(gallery.get("slug", "")).strip()
        if not gallery_id or not gallery_slug:
            continue
        for item_id in list_fanart_gallery_item_ids(gallery_id):
            if item_id not in gallery_slug_by_item_id:
                gallery_slug_by_item_id[item_id] = gallery_slug

    safe_uploader = quote(uploader_profile_key, safe="")
    rows: list[str] = []
    for item in items:
        title = escape(str(item.get("title", "Untitled")))
        item_id = str(item.get("id", "")).strip()
        if item_id:
            link_href = f"/users/{safe_uploader}/gallery/all"
            gallery_slug = gallery_slug_by_item_id.get(item_id, "")
            if gallery_slug:
                link_href = f"/users/{safe_uploader}/gallery/{quote(gallery_slug, safe='')}"
            rows.append(f'<li><a href="{link_href}">{title}</a></li>')
            continue

        image_name = quote(str(item.get("image_filename", "")).strip(), safe="/")
        rows.append(f'<li><a href="/static/fanart/images/{image_name}">{title}</a></li>')
    return '<ul class="work-links">' + "".join(rows) + "</ul>"


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["users"])
    if tail is None or not tail:
        return text_error(response, "Not found", 404)

    profile_key = tail[0].strip()
    if not profile_key:
        return text_error(response, "Not found", 404)

    viewer = current_user(request)
    local_user = get_local_user(profile_key)
    if local_user is None:
        local_user = get_local_user_by_display_name(profile_key)
    if local_user is None:
        return text_error(response, "Not found", 404)

    profile_username = local_user["username"]
    profile_display_name = local_user["display_name"]
    profile_key = profile_display_name if profile_display_name else profile_username
    if len(tail) >= 2 and tail[1] == "gallery":
        gallery_slug = tail[2].strip() if len(tail) >= 3 else "all"
        if not gallery_slug or gallery_slug == "all":
            response.status_code = 303
            response.content_type = "text/plain; charset=utf-8"
            response.headers["Location"] = f"/fanart/{quote(profile_key, safe='')}"
            response.set_data(f"See Other: /fanart/{profile_key}")
            return response

        response.status_code = 303
        response.content_type = "text/plain; charset=utf-8"
        response.headers["Location"] = f"/fanart/{quote(profile_key, safe='')}?gallery={quote(gallery_slug, safe='')}"
        response.set_data(f"See Other: /fanart/{profile_key}?gallery={gallery_slug}")
        return response

    if len(tail) != 1:
        return text_error(response, "Not found", 404)

    uploaded = [work for work in list_works_by_uploader(profile_username) if can_view_work(viewer, work)]
    raw_bookmarks = list_user_bookmarks(profile_username)
    fanart_items = list_fanart_items_by_uploader(profile_username, limit=30)
    visible_bookmarks = [
        row for row in raw_bookmarks if can_view_work(viewer, {"rating": row.get("rating", "Not Rated")})
    ]
    shared_sections_html = render_profile_shared_sections(
        {
            "__PROFILE_UPLOADED_WORKS_HIDDEN_ATTR__": "",
            "__PROFILE_UPLOADED_WORKS_HTML__": _uploaded_works_html(uploaded),
            "__PROFILE_FANART_HIDDEN_ATTR__": "",
            "__PROFILE_FANART_HTML__": _fanart_html(
                profile_username,
                profile_key,
                fanart_items,
            ),
            "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "",
            "__PROFILE_BOOKMARKS_HTML__": _bookmarks_html(visible_bookmarks),
        }
    )

    replacements = {
        "__PROFILE_PAGE_TITLE__": f"FANIC Profile - {escape(profile_display_name)}",
        "__PROFILE_CARD_TITLE__": f"{escape(profile_display_name)}'s Profile",
        "__PROFILE_CARD_SUBTITLE__": "Public profile and uploaded works.",
        "__PROFILE_DETAILS__": f"Display name: {escape(profile_display_name)}",
        "__PROFILE_SHARED_SECTIONS__": shared_sections_html,
    }

    return render_html_template(request, response, "profile-public.html", replacements)
