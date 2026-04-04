from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import NotificationAction
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import (
    parse_notification_action,
)
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import (
    parse_notification_id,
)
from fanic.repository.users import delete_notification
from fanic.repository.users import mark_all_notifications_read
from fanic.repository.users import mark_notification_read


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

    action = parse_notification_action(request.form)
    if action is NotificationAction.MARK_ALL_READ:
        _ = mark_all_notifications_read(username)
        return _redirect(response, "/user/notifications?msg=cleared")

    notification_id = parse_notification_id(request.form)
    if notification_id is None:
        return _redirect(response, "/user/notifications")

    match action:
        case NotificationAction.MARK_READ:
            _ = mark_notification_read(username, notification_id)
            return _redirect(response, "/user/notifications?msg=updated")
        case NotificationAction.DELETE:
            _ = delete_notification(username, notification_id)
            return _redirect(response, "/user/notifications?msg=updated")
        case _:
            return _redirect(response, "/user/notifications")
