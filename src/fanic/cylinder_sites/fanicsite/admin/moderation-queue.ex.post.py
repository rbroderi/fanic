from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.fanart import set_fanart_item_rating
from fanic.repository.moderation_queue import get_moderation_review_item
from fanic.repository.moderation_queue import update_moderation_review_status
from fanic.repository.works import set_work_rating


def _redirect_with_msg(response: ResponseLike, msg: str) -> ResponseLike:
    return _redirect(response, f"/admin/moderation-queue?msg={msg}")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/moderation-queue":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    username = current_user(request)
    if not is_privileged_role(role_for_user(username)):
        return text_error(response, "Forbidden", 403)

    action = request.form.get("action", "").strip().lower()
    queue_id_raw = request.form.get("queue_id", "").strip()
    if action not in {"approve", "reject", "dismiss"}:
        return _redirect_with_msg(response, "invalid")
    if not queue_id_raw.isdigit():
        return _redirect_with_msg(response, "invalid")

    queue_id = int(queue_id_raw)
    item = get_moderation_review_item(queue_id)
    if item is None:
        return _redirect_with_msg(response, "not-found")

    if action == "approve" and str(item["reason_type"]) == "explicit":
        if str(item["content_type"]) == "work":
            updated = set_work_rating(
                str(item["content_id"]),
                "Explicit",
                editor_username=str(username if username else ""),
                edited_by_admin=True,
            )
            if not updated:
                return _redirect_with_msg(response, "rating-failed")
        elif str(item["content_type"]) == "fanart":
            updated = set_fanart_item_rating(str(item["content_id"]), "Explicit")
            if not updated:
                return _redirect_with_msg(response, "rating-failed")

    status_map = {
        "approve": "approved",
        "reject": "rejected",
        "dismiss": "dismissed",
    }
    updated_status = update_moderation_review_status(
        queue_id=queue_id,
        status=status_map[action],
        reviewed_by=str(username if username else ""),
        review_note="",
    )
    if not updated_status:
        return _redirect_with_msg(response, "not-found")

    return _redirect_with_msg(response, status_map[action])
