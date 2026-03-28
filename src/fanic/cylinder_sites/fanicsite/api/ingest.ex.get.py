from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    json_response,
    route_tail,
)
from fanic.ingest_progress import get_progress


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "ingest"])
    if tail is None:
        return json_response(response, {"detail": "Not found"}, 404)

    if tail != ["progress"]:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    if username is None:
        return json_response(response, {"detail": "Login required"}, 401)

    token = request.args.get("token", "").strip()
    if not token:
        return json_response(response, {"detail": "token is required"}, 400)

    progress = get_progress(token)
    if progress is None:
        return json_response(response, {"ok": False, "found": False}, 404)

    return json_response(response, {"ok": True, "found": True, "progress": progress})
