from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.repository import delete_notification
from fanic.repository import mark_all_notifications_read
from fanic.repository import mark_notification_read


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/notifications":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    username = current_user(request)
    if not username:
        return _redirect(response, "/account/login")

    action = request.form.get("notification_action", "").strip()
    if action == "mark-all-read":
        _ = mark_all_notifications_read(username)
        return _redirect(response, "/user/notifications?msg=cleared")

    notification_id_raw = request.form.get("notification_id", "").strip()
    try:
        notification_id = int(notification_id_raw)
    except ValueError:
        return _redirect(response, "/user/notifications")

    if action == "mark-read":
        _ = mark_notification_read(username, notification_id)
        return _redirect(response, "/user/notifications?msg=updated")
    if action == "delete":
        _ = delete_notification(username, notification_id)
        return _redirect(response, "/user/notifications?msg=updated")

    return _redirect(response, "/user/notifications")
