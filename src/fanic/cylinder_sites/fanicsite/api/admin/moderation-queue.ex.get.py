from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import json_response
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.moderation_queue import list_moderation_review_items


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "admin", "moderation-queue"])
    if tail is None or tail:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    if not is_privileged_role(role_for_user(username)):
        return json_response(response, {"detail": "Forbidden"}, 403)

    status = request.args.get("status", "pending").strip().lower()
    limit_raw = request.args.get("limit", "200").strip()
    try:
        limit = int(limit_raw)
    except ValueError:
        return json_response(response, {"detail": "limit must be an integer"}, 422)

    items = list_moderation_review_items(status=status, limit=limit)
    return json_response(response, {"ok": True, "status": status, "count": len(items), "items": items})
