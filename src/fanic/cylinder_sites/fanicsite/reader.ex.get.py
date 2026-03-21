from __future__ import annotations

import json
from html import escape

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    render_html_template,
    route_tail,
    text_error,
)
from fanic.repository import (
    can_view_work,
    get_manifest,
    get_work,
    load_progress,
)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["reader"])
    if tail is None or len(tail) != 1:
        return text_error(response, "Not found", 404)

    work_id = tail[0]
    work = get_work(work_id)
    if not work:
        return text_error(response, "Work not found", 404)

    username = current_user(request)
    if not can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    manifest = get_manifest(work_id)
    if manifest is None:
        return text_error(response, "Work not found", 404)

    user_id = username or "anon"
    page_index = load_progress(work_id, user_id)
    bootstrap_json = json.dumps(
        {
            "work_id": work_id,
            "title": str(manifest.get("title", "FANIC Reader")),
            "work_href": f"/works/{work_id}",
            "user_id": user_id,
            "page_index": page_index,
            "pages": manifest.get("pages", []),
            "chapters": manifest.get("chapters", []),
        },
        ensure_ascii=True,
    ).replace("<", "\\u003c")

    return render_html_template(
        request,
        response,
        "reader.html",
        {
            "__READER_TITLE__": escape(str(manifest.get("title", "FANIC Reader"))),
            "__READER_WORK_HREF__": escape(f"/works/{work_id}"),
            "__READER_BOOTSTRAP_JSON__": bootstrap_json,
        },
    )
