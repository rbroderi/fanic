from collections.abc import Sequence
from html import escape

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.repository import NotificationRow
from fanic.repository import list_user_notifications


def _notifications_html(rows: Sequence[NotificationRow]) -> str:
    if not rows:
        return '<p class="profile-meta">No notifications yet.</p>'

    items: list[str] = []
    for row in rows:
        notification_id = escape(str(row.get("id", "0")))
        actor = escape(str(row.get("actor_username", "someone")))
        message = escape(str(row.get("message", "")))
        href = escape(str(row.get("href", "")))
        created_at = escape(str(row.get("created_at", "")))
        is_read = bool(row.get("is_read", False))
        unread_label = "" if is_read else '<strong class="status-text">New</strong> '
        view_html = f'<a class="user-menu-link" href="{href}">View</a>' if href else ""

        items.append(
            '<article class="card comment-card">'
            + f'<p class="comment-meta">{unread_label}From {actor} at {created_at}</p>'
            + f"<p>{message}</p>"
            + '<div style="display:flex; gap:0.5rem; flex-wrap:wrap;">'
            + view_html
            + (
                f'<form method="post" action="/user/notifications"><input type="hidden" name="notification_action" value="mark-read" /><input type="hidden" name="notification_id" value="{notification_id}" /><button type="submit">Mark read</button></form>'
                if not is_read
                else ""
            )
            + f'<form method="post" action="/user/notifications"><input type="hidden" name="notification_action" value="delete" /><input type="hidden" name="notification_id" value="{notification_id}" /><button class="button-muted" type="submit">Delete</button></form>'
            + "</div>"
            + "</article>"
        )

    return "".join(items)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/user/notifications":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if not username:
        return render_html_template(
            request,
            response,
            "notification.html",
            {
                "__NOTIFICATION_STATUS__": "Login required to view notifications.",
                "__NOTIFICATION_STATUS_CLASS__": "error",
                "__NOTIFICATION_STATUS_HIDDEN_ATTR__": "",
                "__NOTIFICATION_UNREAD_COUNT__": "0",
                "__NOTIFICATION_MARK_ALL_HIDDEN_ATTR__": "hidden",
                "__NOTIFICATION_ITEMS_HTML__": '<p class="profile-meta">Use <a href="/account/login">Login</a> to sign in.</p>',
            },
        )

    rows = list_user_notifications(username, limit=200)
    unread_count = sum(1 for row in rows if not bool(row.get("is_read", False)))

    status_msg = request.args.get("msg", "").strip()
    status_text = ""
    status_class = ""
    status_hidden = "hidden"
    if status_msg == "updated":
        status_text = "Notification updated."
        status_class = "success"
        status_hidden = ""
    elif status_msg == "cleared":
        status_text = "All notifications marked as read."
        status_class = "success"
        status_hidden = ""

    return render_html_template(
        request,
        response,
        "notification.html",
        {
            "__NOTIFICATION_STATUS__": status_text,
            "__NOTIFICATION_STATUS_CLASS__": status_class,
            "__NOTIFICATION_STATUS_HIDDEN_ATTR__": status_hidden,
            "__NOTIFICATION_UNREAD_COUNT__": escape(str(unread_count)),
            "__NOTIFICATION_MARK_ALL_HIDDEN_ATTR__": "" if rows else "hidden",
            "__NOTIFICATION_ITEMS_HTML__": _notifications_html(rows),
        },
    )
