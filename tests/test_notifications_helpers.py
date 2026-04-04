from typing import final

from fanic.cylinder_sites.fanicsite.user.notifications_helpers import NotificationAction
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import (
    notification_status,
)
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import (
    parse_notification_action,
)
from fanic.cylinder_sites.fanicsite.user.notifications_helpers import (
    parse_notification_id,
)


@final
class _FormStub:
    def __init__(self, values: dict[str, str]) -> None:
        self._values: dict[str, str] = values

    def get(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


def test_notification_status_mapping() -> None:
    updated = notification_status("updated")
    assert updated.text == "Notification updated."
    assert updated.css_class == "success"
    assert updated.hidden_attr == ""

    cleared = notification_status("cleared")
    assert cleared.text == "All notifications marked as read."
    assert cleared.css_class == "success"
    assert cleared.hidden_attr == ""

    default = notification_status("other")
    assert default.text == ""
    assert default.css_class == ""
    assert default.hidden_attr == "hidden"


def test_parse_notification_action() -> None:
    assert (
        parse_notification_action(_FormStub({"notification_action": "mark-all-read"}))
        is NotificationAction.MARK_ALL_READ
    )
    assert parse_notification_action(_FormStub({"notification_action": "mark-read"})) is NotificationAction.MARK_READ
    assert parse_notification_action(_FormStub({"notification_action": "delete"})) is NotificationAction.DELETE
    assert parse_notification_action(_FormStub({"notification_action": "unknown"})) is None


def test_parse_notification_id() -> None:
    assert parse_notification_id(_FormStub({"notification_id": "12"})) == 12
    assert parse_notification_id(_FormStub({"notification_id": "abc"})) is None
    assert parse_notification_id(_FormStub({})) is None
