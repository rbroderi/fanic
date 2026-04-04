from html import escape
from urllib.parse import urlencode

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.editor_metadata import render_common_tag_datalist_replacements
from fanic.cylinder_sites.fanicsite_home_helpers import aria_current as _aria_current
from fanic.cylinder_sites.fanicsite_home_helpers import (
    fanart_items_html as _fanart_items_html,
)
from fanic.cylinder_sites.fanicsite_home_helpers import selected_attr as _selected_attr
from fanic.cylinder_sites.fanicsite_home_helpers import (
    work_grid_html as _work_grid_html,
)
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.fanart import list_fanart_items
from fanic.repository.users import list_local_users
from fanic.repository.works import list_works
from fanic.repository.works import user_prefers_explicit
from fanic.repository.works import user_prefers_mature

COMICS_PER_PAGE = 120


def _render_user_datalist_options(limit: int = 400) -> str:
    users = list_local_users(offset=0, limit=limit)
    seen: set[str] = set()
    parts: list[str] = []
    for user_row in users:
        username = str(user_row.get("username", "")).strip()
        display_name = str(user_row.get("display_name", "")).strip()
        values = [display_name, username]
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            parts.append(f'<option value="{escape(normalized)}"></option>')
    return "".join(parts)


_USER_OPTIONS_HTML = _render_user_datalist_options()
_COMMON_TAG_DATALIST_REPLACEMENTS = render_common_tag_datalist_replacements()
_SEARCH_TAG_DATALIST_REPLACEMENTS = {
    "__FANDOM_OPTIONS_HTML__": _COMMON_TAG_DATALIST_REPLACEMENTS.get("__FANDOM_OPTIONS_HTML__", ""),
    "__FREEFORM_OPTIONS_HTML__": _COMMON_TAG_DATALIST_REPLACEMENTS.get("__FREEFORM_OPTIONS_HTML__", ""),
}


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/":
        return text_error(response, "Not found", 404)

    view = request.args.get("view", "comics").strip().lower()
    view = view if view in {"comics", "fanart"} else "comics"
    q = request.args.get("q", "").strip()
    user = request.args.get("user", "").strip()
    fandom = request.args.get("fandom", "").strip()
    tag = request.args.get("tag", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "newest").strip()
    page_raw = request.args.get("page", "").strip()
    try:
        page = max(1, int(page_raw)) if page_raw else 1
    except ValueError:
        page = 1

    filters = {
        "q": q,
        "user": user,
        "fandom": fandom,
        "tag": tag,
        "status": status,
        "sort": sort,
    }
    username = current_user(request)
    can_delete = is_privileged_role(role_for_user(username))
    query_string = urlencode({"view": view, **filters})
    back_href = f"{request.path}?{query_string}" if query_string else request.path

    work_grid_html = ""
    view_hidden_input = (
        '<input type="hidden" name="view" value="fanart" />'
        if view == "fanart"
        else '<input type="hidden" name="view" value="comics" />'
    )
    if view == "fanart":
        fanart_filters = {
            "q": q,
            "user": user,
            "fandom": fandom,
            "tag": tag,
            "status": status,
            "sort": sort,
        }
        fanart_items = list_fanart_items(filters=fanart_filters, limit=120)
        work_grid_html = _fanart_items_html(
            fanart_items,
            back_href=back_href,
            can_delete=can_delete,
        )
    else:
        include_mature = user_prefers_mature(username)
        include_explicit = user_prefers_explicit(username)
        comics_filters = {
            **filters,
            "limit": str(COMICS_PER_PAGE),
            "offset": str((page - 1) * COMICS_PER_PAGE),
            "include_mature": "1" if include_mature else "0",
            "include_explicit": "1" if include_explicit else "0",
        }
        works = list_works(comics_filters)
        work_grid_html = _work_grid_html(works, can_delete, back_href=back_href)

    return render_html_template(
        request,
        response,
        "index.html",
        {
            "__HOME_VIEW_CLASS__": f"home-view-{view}",
            "__COMICS_TAB_CURRENT__": _aria_current(view == "comics"),
            "__FANART_TAB_CURRENT__": _aria_current(view == "fanart"),
            "__VIEW_TAGLINE_HIDDEN_ATTR__": "" if view == "fanart" else "hidden",
            "__USER_MENU_UPLOAD_LINK__": (
                (
                    '<a class="user-menu-link" href="/fanart/upload">Upload fanart</a>'
                    if view == "fanart"
                    else '<a class="user-menu-link" href="/comic/upload">Upload comic</a>'
                )
                if username
                else ""
            ),
            "__VIEW_HIDDEN_INPUT__": view_hidden_input,
            "__FILTER_Q__": escape(q),
            "__FILTER_USER__": escape(user),
            "__USER_OPTIONS_HTML__": _USER_OPTIONS_HTML,
            "__FILTER_FANDOM__": escape(fandom),
            "__FILTER_TAG__": escape(tag),
            "__FILTER_ACTION__": "/",
            "__STATUS_ANY_SELECTED__": _selected_attr(status, ""),
            "__STATUS_COMPLETE_SELECTED__": _selected_attr(status, "complete"),
            "__STATUS_IN_PROGRESS_SELECTED__": _selected_attr(status, "in_progress"),
            "__SORT_NEWEST_SELECTED__": _selected_attr(sort, "newest"),
            "__SORT_OLDEST_SELECTED__": _selected_attr(sort, "oldest"),
            "__SORT_TITLE_ASC_SELECTED__": _selected_attr(sort, "title_asc"),
            "__SORT_TITLE_DESC_SELECTED__": _selected_attr(sort, "title_desc"),
            "__WORK_GRID_HTML__": work_grid_html,
            **_SEARCH_TAG_DATALIST_REPLACEMENTS,
        },
    )
