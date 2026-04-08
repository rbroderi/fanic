from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import json_response
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.fanart import set_fanart_item_rating
from fanic.repository.moderation_queue import get_moderation_review_item
from fanic.repository.moderation_queue import update_moderation_review_status
from fanic.repository.works import set_work_rating


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "admin", "moderation-queue"])
    if tail is None or tail:
        return json_response(response, {"detail": "Not found"}, 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return json_response(response, {"detail": "Invalid CSRF token"}, 403)

    username = current_user(request)
    if not is_privileged_role(role_for_user(username)):
        return json_response(response, {"detail": "Forbidden"}, 403)

    action = request.form.get("action", "").strip().lower()
    queue_id_raw = request.form.get("queue_id", "").strip()
    review_note = request.form.get("review_note", "").strip()

    if action not in {"approve", "reject", "dismiss"}:
        return json_response(response, {"detail": "Invalid action"}, 422)
    if not queue_id_raw.isdigit():
        return json_response(response, {"detail": "queue_id must be an integer"}, 422)

    queue_id = int(queue_id_raw)
    item = get_moderation_review_item(queue_id)
    if item is None:
        return json_response(response, {"detail": "Queue item not found"}, 404)

    if action == "approve" and str(item["reason_type"]) == "explicit":
        if str(item["content_type"]) == "work":
            ok = set_work_rating(
                str(item["content_id"]),
                "Explicit",
                editor_username=str(username if username else ""),
                edited_by_admin=True,
            )
        else:
            ok = set_fanart_item_rating(str(item["content_id"]), "Explicit")
        if not ok:
            return json_response(response, {"detail": "Failed to update rating"}, 409)

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "dismiss": "dismissed",
    }
    queue_status = status_map[action]
    updated = update_moderation_review_status(
        queue_id=queue_id,
        status=queue_status,
        reviewed_by=str(username if username else ""),
        review_note=review_note,
    )
    if not updated:
        return json_response(response, {"detail": "Queue item not found"}, 404)

    return json_response(response, {"ok": True, "queue_id": queue_id, "status": queue_status})
