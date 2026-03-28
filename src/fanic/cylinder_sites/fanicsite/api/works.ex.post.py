from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import route_tail
from fanic.repository import save_progress
from fanic.repository import upsert_user_bookmark


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "works"])
    if tail is None or len(tail) != 2:
        return json_response(response, {"detail": "Not found"}, 404)

    work_id = tail[0]
    if tail[1] == "progress":
        user_id = request.args.get("user_id", "anon")

        page_index_raw = request.args.get("page_index", "1")
        try:
            page_index = int(page_index_raw)
        except ValueError:
            return json_response(
                response,
                {"detail": "page_index must be an integer"},
                422,
            )

        if page_index < 1:
            return json_response(response, {"detail": "page_index must be >= 1"}, 422)

        save_progress(work_id, user_id, page_index)
        return json_response(response, {"ok": True, "page_index": page_index})

    if tail[1] == "bookmark":
        user_id = request.form.get("user_id", "").strip()
        if not user_id:
            user_id = request.args.get("user_id", "").strip()

        if not user_id or user_id == "anon":
            return json_response(response, {"detail": "Authentication required"}, 401)

        message = request.form.get("message", "").strip()
        if not message:
            message = request.args.get("message", "").strip()
        if len(message) > 1024:
            return json_response(
                response,
                {"detail": "message must be <= 1024 characters"},
                422,
            )

        page_index_raw = request.form.get("page_index", "").strip()
        if not page_index_raw:
            page_index_raw = request.args.get("page_index", "1")
        try:
            page_index = int(page_index_raw)
        except ValueError:
            return json_response(
                response,
                {"detail": "page_index must be an integer"},
                422,
            )

        if page_index < 1:
            return json_response(response, {"detail": "page_index must be >= 1"}, 422)

        saved = upsert_user_bookmark(
            user_id,
            work_id,
            page_index=page_index,
            message=message,
        )
        if not saved:
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"ok": True, "page_index": page_index})

    return json_response(response, {"detail": "Not found"}, 404)
