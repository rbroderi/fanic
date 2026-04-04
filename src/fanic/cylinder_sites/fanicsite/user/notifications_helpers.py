from enum import StrEnum

from fanic.cylinder_sites.common.protocols import FormLike
from fanic.cylinder_sites.common.protocols import StatusReplacements
from fanic.cylinder_sites.common.protocols import status_hidden
from fanic.cylinder_sites.common.protocols import status_visible


class NotificationAction(StrEnum):
    MARK_ALL_READ = "mark-all-read"
    MARK_READ = "mark-read"
    DELETE = "delete"


def notification_status(msg: str) -> StatusReplacements:
    match msg.strip():
        case "updated":
            return status_visible("Notification updated.", "success")
        case "cleared":
            return status_visible("All notifications marked as read.", "success")
        case _:
            return status_hidden()


def parse_notification_action(form: FormLike) -> NotificationAction | None:
    action_raw = form.get("notification_action", "").strip()
    match action_raw:
        case NotificationAction.MARK_ALL_READ.value:
            return NotificationAction.MARK_ALL_READ
        case NotificationAction.MARK_READ.value:
            return NotificationAction.MARK_READ
        case NotificationAction.DELETE.value:
            return NotificationAction.DELETE
        case _:
            return None


def parse_notification_id(form: FormLike) -> int | None:
    notification_id_raw = form.get("notification_id", "").strip()
    try:
        return int(notification_id_raw)
    except ValueError:
        return None
