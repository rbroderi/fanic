from html import escape
from urllib.parse import quote

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.profile_shared import render_bookmarks_html
from fanic.cylinder_sites.profile_shared import render_fanart_html
from fanic.cylinder_sites.profile_shared import render_profile_shared_sections
from fanic.cylinder_sites.profile_shared import render_uploaded_works_html
from fanic.repository import can_view_work
from fanic.repository import get_local_user
from fanic.repository import get_local_user_by_display_name
from fanic.repository import list_fanart_items_by_uploader
from fanic.repository import list_user_bookmarks
from fanic.repository import list_works_by_uploader


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
            "__PROFILE_UPLOADED_WORKS_HTML__": render_uploaded_works_html(
                uploaded,
                include_stats=False,
            ),
            "__PROFILE_FANART_HIDDEN_ATTR__": "",
            "__PROFILE_FANART_HTML__": render_fanart_html(
                profile_username,
                profile_key,
                fanart_items,
                profile_kind="public",
            ),
            "__PROFILE_BOOKMARKS_HIDDEN_ATTR__": "",
            "__PROFILE_BOOKMARKS_HTML__": render_bookmarks_html(visible_bookmarks),
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
