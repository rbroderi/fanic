from __future__ import annotations

from collections.abc import Sequence
from html import escape

from fanic.cylinder_sites.common import ADMIN_USERNAME
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import rating_badge_html
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.repository import WorkListItem
from fanic.repository import can_view_work
from fanic.repository import list_works


def _work_grid_html(works: Sequence[WorkListItem], can_delete: bool) -> str:
    if not works:
        return "<p>No works yet. Ingest a CBZ to get started.</p>"

    parts: list[str] = []
    for work in works:
        work_id = escape(str(work.get("id", "")))
        title = escape(str(work.get("title", "Untitled")))
        summary_raw = str(work.get("summary", ""))
        summary = escape(summary_raw if summary_raw else "No summary yet.")
        rating_html = rating_badge_html(work.get("rating", "Not Rated"))
        status = escape(str(work.get("status", "in_progress")))
        page_count = escape(str(work.get("page_count", 0)))
        cover_index = escape(str(work.get("cover_page_index", 1)))

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
            """
      <article class="card work-card">
        {delete_html}
        <a href="/works/{work_id}">
          <img class="work-cover" src="/api/works/{work_id}/pages/{cover_index}/thumb" alt="{title} cover" loading="lazy" />
        </a>
        <h3><a href="/works/{work_id}">{title}</a></h3>
        <p class="work-meta">{rating_html} | {status} | {page_count} pages</p>
        <p>{summary}</p>
      </article>
    """.format(
                delete_html=delete_html,
                work_id=work_id,
                cover_index=cover_index,
                title=title,
                rating_html=rating_html,
                status=status,
                page_count=page_count,
                summary=summary,
            )
        )

    return "".join(parts)


def _selected_attr(actual: str, expected: str) -> str:
    return "selected" if actual == expected else ""


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/":
        return text_error(response, "Not found", 404)

    q = request.args.get("q", "").strip()
    fandom = request.args.get("fandom", "").strip()
    tag = request.args.get("tag", "").strip()
    status = request.args.get("status", "").strip()
    sort = request.args.get("sort", "newest").strip()
    filters = {
        "q": q,
        "fandom": fandom,
        "tag": tag,
        "status": status,
        "sort": sort,
    }
    username = current_user(request)
    works = [work for work in list_works(filters) if can_view_work(username, work)]
    can_delete = username == ADMIN_USERNAME

    return render_html_template(
        request,
        response,
        "index.html",
        {
            "__FILTER_Q__": escape(q),
            "__FILTER_FANDOM__": escape(fandom),
            "__FILTER_TAG__": escape(tag),
            "__FILTER_ACTION__": "/",
            "__BROWSE_ARIA_CURRENT__": 'aria-current="page"',
            "__STATUS_ANY_SELECTED__": _selected_attr(status, ""),
            "__STATUS_COMPLETE_SELECTED__": _selected_attr(status, "complete"),
            "__STATUS_IN_PROGRESS_SELECTED__": _selected_attr(status, "in_progress"),
            "__SORT_NEWEST_SELECTED__": _selected_attr(sort, "newest"),
            "__SORT_OLDEST_SELECTED__": _selected_attr(sort, "oldest"),
            "__SORT_TITLE_ASC_SELECTED__": _selected_attr(sort, "title_asc"),
            "__SORT_TITLE_DESC_SELECTED__": _selected_attr(sort, "title_desc"),
            "__WORK_GRID_HTML__": _work_grid_html(works, can_delete),
        },
    )
