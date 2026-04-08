from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.protocols import status_for_message
from fanic.cylinder_sites.common.protocols import status_visible
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.moderation_queue import list_moderation_review_items


def _status_text(msg: str) -> tuple[str, str, str]:
    status = status_for_message(
        msg,
        {
            "approved": status_visible("Queue item approved.", "success"),
            "rejected": status_visible("Queue item rejected.", "success"),
            "dismissed": status_visible("Queue item dismissed.", "success"),
            "not-found": status_visible("Queue item not found.", "error"),
            "invalid": status_visible("Invalid moderation queue action.", "error"),
            "rating-failed": status_visible("Unable to update rating for this item.", "error"),
        },
    )
    return status.text, status.css_class, status.hidden_attr


def _rows_html() -> str:
    rows = list_moderation_review_items(status="pending", limit=200)
    if not rows:
        return '<tr><td colspan="9">No pending moderation review items.</td></tr>'

    html_rows: list[str] = []
    for row in rows:
        row_id = int(row["id"])
        reason_type = escape(str(row["reason_type"]))
        content_type = escape(str(row["content_type"]))
        content_id = escape(str(row["content_id"]))
        content_href = escape(str(row["content_href"]))
        content_title = escape(str(row["content_title"])) if str(row["content_title"]) else content_id
        uploader = escape(str(row["uploader_username"]))
        source_member = escape(str(row["source_member"]))
        confidence = f"{float(row['confidence']):.4f}"
        thresholds = f"[{float(row['min_threshold']):.2f}, {float(row['max_threshold']):.2f})"
        created_at = escape(str(row["created_at"]))

        html_rows.append(
            """
            <tr>
                <td>{id}</td>
                <td>{reason}</td>
                <td>{type}</td>
                <td><a href="{href}">{title}</a></td>
                <td>{uploader}</td>
                <td>{source_member}</td>
                <td>{confidence}<br /><span class="profile-meta">{thresholds}</span></td>
                <td>{created_at}</td>
                <td>
                    <form method="post" action="/admin/moderation-queue" class="upload-form">
                        <input type="hidden" name="queue_id" value="{id}" />
                        <input type="hidden" name="action" value="approve" />
                        <button type="submit">Approve</button>
                    </form>
                    <form method="post" action="/admin/moderation-queue" class="upload-form" style="margin-top: 0.5rem;">
                        <input type="hidden" name="queue_id" value="{id}" />
                        <input type="hidden" name="action" value="reject" />
                        <button type="submit" class="button-muted">Reject</button>
                    </form>
                    <form method="post" action="/admin/moderation-queue" class="upload-form" style="margin-top: 0.5rem;">
                        <input type="hidden" name="queue_id" value="{id}" />
                        <input type="hidden" name="action" value="dismiss" />
                        <button type="submit" class="button-muted">Dismiss</button>
                    </form>
                </td>
            </tr>
            """.format(
                id=row_id,
                reason=reason_type,
                type=content_type,
                href=content_href,
                title=content_title,
                uploader=uploader,
                source_member=source_member,
                confidence=confidence,
                thresholds=escape(thresholds),
                created_at=created_at,
            )
        )
    return "".join(html_rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/moderation-queue":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if not is_privileged_role(role_for_user(username)):
        return text_error(response, "Forbidden", 403)

    msg = request.args.get("msg", "").strip()
    status_text, status_class, status_hidden_attr = _status_text(msg)

    return render_html_template(
        request,
        response,
        "moderation-queue.html",
        {
            "__MODERATION_QUEUE_ROWS_HTML__": _rows_html(),
            "__MODERATION_QUEUE_STATUS_TEXT__": escape(status_text),
            "__MODERATION_QUEUE_STATUS_CLASS__": escape(status_class),
            "__MODERATION_QUEUE_STATUS_HIDDEN_ATTR__": status_hidden_attr,
        },
    )
