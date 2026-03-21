from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    json_response,
    route_tail,
)
from fanic.repository import save_progress


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "works"])
    if tail is None or len(tail) != 2 or tail[1] != "progress":
        return json_response(response, {"detail": "Not found"}, 404)

    work_id = tail[0]
    user_id = request.args.get("user_id", "anon")

    page_index_raw = request.args.get("page_index", "1")
    try:
        page_index = int(page_index_raw)
    except ValueError:
        return json_response(response, {"detail": "page_index must be an integer"}, 422)

    if page_index < 1:
        return json_response(response, {"detail": "page_index must be >= 1"}, 422)

    save_progress(work_id, user_id, page_index)
    return json_response(response, {"ok": True, "page_index": page_index})
