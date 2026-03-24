from __future__ import annotations

from collections.abc import Sequence
from html import escape
from urllib.parse import quote
from urllib.parse import urlencode

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import media_url
from fanic.cylinder_sites.common import rating_badge_html
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import text_error
from fanic.repository import FanartItemRow
from fanic.repository import WorkListItem
from fanic.repository import can_view_work
from fanic.repository import list_fanart_items
from fanic.repository import list_works


def _work_grid_html(
    works: Sequence[WorkListItem],
    can_delete: bool,
    *,
    back_href: str,
) -> str:
    if not works:
        return "<p>No works yet. Ingest a CBZ to get started.</p>"

    parts: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        work_id_raw = str(work.get("id", "")).strip()
        if not work_id_raw:
            continue
        work_href = (
            f"/works/{quote(work_id_raw, safe='')}?back={quote(back_href, safe='')}"
        )
        title = escape(str(work.get("title", "Untitled")))
        summary_raw = str(work.get("summary", ""))
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        rating_html = rating_badge_html(work.get("rating", "Not Rated"))
        status = escape(str(work.get("status", "in_progress")))
        page_count = escape(str(work.get("page_count", 0)))
        cover_thumb_name = str(work.get("cover_thumb_filename", "")).strip()
        work_id_quoted = quote(str(work.get("id", "")), safe="")
        if cover_thumb_name:
            cover_src = media_url(
                f"/works/{work_id_quoted}/thumbs/{quote(cover_thumb_name, safe='/')}"
            )
        else:
            cover_src = media_url("/static/logo.png")

        delete_html = ""
        if can_delete:
            delete_html = """
        <form method=\"post\" action=\"/works/{work_id}/delete\" class=\"admin-delete-form\" onsubmit=\"return confirm('Delete this comic? This cannot be undone.');\">
          <button type=\"submit\" class=\"icon-delete-button\" title=\"Delete comic\" aria-label=\"Delete comic\">
            <i class=\"fa-solid fa-trash\" aria-hidden=\"true\"></i>
          </button>
        </form>
      """.format(work_id=work_id)

        parts.append(
            f"""
      <article class="card work-card">
        {delete_html}
                <a href="{work_href}">
          <img class="work-cover" src="{cover_src}" alt="{title} cover" loading="lazy" />
        </a>
                <h3><a href="{work_href}">{title}</a></h3>
        <p class="work-meta">{rating_html} | {status} | {page_count} pages</p>
        <p>{summary}</p>
      </article>
    """
        )

    return "".join(parts)


def _selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def _aria_current(is_current: bool) -> str:
    return 'aria-current="page"' if is_current else ""


def _fanart_items_html(items: Sequence[FanartItemRow], *, back_href: str) -> str:
    if not items:
        return "<p>No fanart matches found.</p>"

    parts: list[str] = []
    for row in items:
        uploader = str(row.get("uploader_username", "")).strip()
        if not uploader:
            continue
        item_id = str(row.get("id", "")).strip()
        if not item_id:
            continue

        safe_uploader = escape(uploader)
        safe_item_id = quote(item_id, safe="")
        uploader_href = f"/fanart/{quote(uploader, safe='')}"
        viewer_href = f"{uploader_href}/reader?item_id={safe_item_id}&back={quote(back_href, safe='')}"
        title_raw = str(row.get("title", "Untitled"))
        title = escape(title_raw)
        summary_raw = str(row.get("summary", "")).strip()
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        rating_html = rating_badge_html(row.get("rating", "Not Rated"))
        created_at = escape(str(row.get("created_at", "")))
        image_name = str(row.get("image_filename", "")).strip()
        claimed_url = (
            f"/fanart/images/{quote(image_name, safe='/')}"
            if image_name
            else viewer_href
        )
        report_href = (
            "/dmca?issue_type=copyright-dmca"
            f"&work_title={quote(title_raw, safe='')}"
            f"&claimed_url={quote(claimed_url, safe='')}"
        )
        thumb_name = str(row.get("thumb_filename", "")).strip()
        if thumb_name:
            thumb_src = f"/fanart/thumbs/{quote(thumb_name, safe='/')}"
        else:
            thumb_src = "/static/logo.png"

        parts.append(
            f'''
      <article class="card work-card">
                <a href="{viewer_href}">
          <img class="work-cover" src="{thumb_src}" alt="{safe_uploader} fanart preview" loading="lazy" />
        </a>
        <h3><a href="{viewer_href}">{title}</a></h3>
                <h3><a href="{uploader_href}">@{safe_uploader}</a></h3>
        <p class="work-meta">{rating_html} | {created_at}</p>
        <p>{summary}</p>
        <p><a href="{report_href}">Report</a></p>
      </article>
    '''
        )

    return "".join(parts)


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
    filters = {
        "q": q,
        "user": user,
        "fandom": fandom,
        "tag": tag,
        "status": status,
        "sort": sort,
    }
    username = current_user(request)
    can_delete = role_for_user(username) in {"superadmin", "admin"}
    query_string = urlencode(request.args)
    back_href = f"{request.path}?{query_string}" if query_string else request.path

    work_grid_html = ""
    view_hidden_input = f'<input type="hidden" name="view" value="{escape(view)}" />'
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
        work_grid_html = _fanart_items_html(fanart_items, back_href=back_href)
    else:
        works = [work for work in list_works(filters) if can_view_work(username, work)]
        work_grid_html = _work_grid_html(works, can_delete, back_href=back_href)

    return render_html_template(
        request,
        response,
        "index.html",
        {
            "__HOME_VIEW_CLASS__": f"home-view-{view}",
            "__COMICS_TAB_CURRENT__": _aria_current(view == "comics"),
            "__FANART_TAB_CURRENT__": _aria_current(view == "fanart"),
            "__USER_MENU_UPLOAD_LINK__": (
                (
                    '<a class="user-menu-link" href="/fanart/upload">Upload fanart</a>'
                    if view == "fanart"
                    else '<a class="user-menu-link" href="/ingest">Upload comic</a>'
                )
                if username
                else ""
            ),
            "__VIEW_HIDDEN_INPUT__": view_hidden_input,
            "__FILTER_Q__": escape(q),
            "__FILTER_USER__": escape(user),
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
        },
    )
