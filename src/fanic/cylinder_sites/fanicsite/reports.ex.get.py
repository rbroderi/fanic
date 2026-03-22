from __future__ import annotations

from html import escape

from fanic.cylinder_sites.common import ADMIN_USERNAME
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.report_issues import report_issue_label
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.repository import ContentReportRow
from fanic.repository import list_content_reports

REPORT_STATUS_OPTIONS: list[tuple[str, str]] = [
    ("open", "Open"),
    ("re-open", "Re-open"),
    ("resolved", "Resolved"),
    ("false-report", "False report"),
    ("needs-research", "More research needed"),
]


def _report_status_options_html(selected: str) -> str:
    normalized_selected = selected.strip()
    options: list[str] = []
    for value, label in REPORT_STATUS_OPTIONS:
        selected_attr = " selected" if normalized_selected == value else ""
        options.append(
            f'<option value="{escape(value)}"{selected_attr}>{escape(label)}</option>'
        )
    return "".join(options)


def _report_status_label(status: str) -> str:
    normalized = status.strip()
    for value, label in REPORT_STATUS_OPTIONS:
        if normalized == value:
            return label
    return normalized if normalized else "Open"


def _report_rows_html(
    reports: list[ContentReportRow],
    *,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
) -> str:
    if not reports:
        return '<p class="profile-meta">No reports found for the selected filters.</p>'

    rows: list[str] = []
    filter_work_id = work_id
    filter_issue_type = issue_type
    filter_status = status
    filter_start_date = start_date
    filter_end_date = end_date

    for report in reports:
        report_id = escape(str(report["id"]))
        created_at = escape(report["created_at"])
        issue_type = escape(report["issue_type"])
        issue_label = escape(report_issue_label(report["issue_type"]))
        report_status_raw = report["status"]
        report_status = escape(report_status_raw)
        report_status_label = escape(_report_status_label(report_status_raw))
        work_id_raw = report["work_id"]
        report_work_id = escape(work_id_raw) if work_id_raw is not None else ""
        work_title = escape(report["work_title"] if report["work_title"] else "")
        reporter_name = escape(report["reporter_name"])
        reporter_email = escape(report["reporter_email"])
        claimed_url = escape(report["claimed_url"])
        evidence_url = escape(report["evidence_url"])
        details = escape(report["details"]).replace("\n", "<br />")
        reporter_username = escape(report["reporter_username"])

        work_display = (
            f"{work_title} ({report_work_id})"
            if work_title and report_work_id
            else (
                work_title
                if work_title
                else (report_work_id if report_work_id else "-")
            )
        )
        reporter_display = (
            f"{reporter_name} ({reporter_username})"
            if reporter_username
            else reporter_name
        )

        evidence_html = (
            f'<a href="{evidence_url}" target="_blank" rel="noopener noreferrer">Evidence</a>'
            if evidence_url
            else "-"
        )

        rows.append(
            '<article class="card comment-card">'
            + f'<p class="comment-meta"><strong>Report #{report_id}</strong> | {created_at}</p>'
            + f'<p><strong>Type:</strong> {issue_label} <span class="profile-meta">({issue_type})</span></p>'
            + f'<p><strong>Status:</strong> {report_status_label} <span class="profile-meta">({report_status})</span></p>'
            + f"<p><strong>Work:</strong> {work_display}</p>"
            + f"<p><strong>Reporter:</strong> {reporter_display} | {reporter_email}</p>"
            + f'<p><strong>Claimed URL:</strong> <a href="{claimed_url}" target="_blank" rel="noopener noreferrer">{claimed_url}</a></p>'
            + f"<p><strong>Evidence:</strong> {evidence_html}</p>"
            + f"<p><strong>Details:</strong><br />{details}</p>"
            + '<form class="upload-form" method="post" action="/reports" style="margin-top:0.75rem;">'
            + f'<input type="hidden" name="report_id" value="{report_id}" />'
            + f'<input type="hidden" name="report_work_id" value="{report_work_id}" />'
            + f'<input type="hidden" name="work_id" value="{escape(filter_work_id)}" />'
            + f'<input type="hidden" name="issue_type" value="{escape(filter_issue_type)}" />'
            + f'<input type="hidden" name="status" value="{escape(filter_status)}" />'
            + f'<input type="hidden" name="start_date" value="{escape(filter_start_date)}" />'
            + f'<input type="hidden" name="end_date" value="{escape(filter_end_date)}" />'
            + '<button type="submit" name="report_action" value="mark-resolved" class="button-muted">Mark resolved</button> '
            + '<button type="submit" name="report_action" value="mark-reopen" class="button-muted">Mark re-open</button> '
            + '<button type="submit" name="report_action" value="mark-false" class="button-muted">Mark false</button> '
            + '<button type="submit" name="report_action" value="mark-research" class="button-muted">Mark more research needed</button> '
            + '<button type="submit" name="report_action" value="promote-explicit" class="button-muted">Promote to explicit rating</button> '
            + '<button type="submit" name="report_action" value="remove" class="button-danger" onclick="return confirm(\'Remove this report item?\');">Remove item</button>'
            + "</form>"
            + "</article>"
        )
    return "".join(rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/reports":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if username != ADMIN_USERNAME:
        return text_error(response, "Forbidden", 403)

    msg = request.args.get("msg", "").strip()
    work_id = request.args.get("work_id", "").strip()
    issue_type = request.args.get("issue_type", "").strip()
    status = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    status_text = ""
    status_class = ""
    status_hidden = "hidden"
    if msg == "removed":
        status_text = "Report removed."
        status_class = "success"
        status_hidden = ""
    elif msg == "marked-false":
        status_text = "Report marked as false report."
        status_class = "success"
        status_hidden = ""
    elif msg == "marked-research":
        status_text = "Report marked as more research needed."
        status_class = "success"
        status_hidden = ""
    elif msg == "marked-resolved":
        status_text = "Report marked as resolved."
        status_class = "success"
        status_hidden = ""
    elif msg == "marked-reopen":
        status_text = "Report marked as re-open."
        status_class = "success"
        status_hidden = ""
    elif msg == "promoted-explicit":
        status_text = "Work rating promoted to Explicit and report marked resolved."
        status_class = "success"
        status_hidden = ""
    elif msg == "promote-missing-work":
        status_text = "Cannot promote rating: report is not linked to a work id."
        status_class = "error"
        status_hidden = ""
    elif msg == "promote-work-not-found":
        status_text = "Cannot promote rating: linked work was not found."
        status_class = "error"
        status_hidden = ""
    elif msg == "not-found":
        status_text = "Report not found."
        status_class = "error"
        status_hidden = ""
    elif msg == "invalid-id":
        status_text = "Invalid report id."
        status_class = "error"
        status_hidden = ""
    elif msg == "invalid-action":
        status_text = "Invalid report action."
        status_class = "error"
        status_hidden = ""

    reports = list_content_reports(
        work_id=work_id,
        issue_type=issue_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )

    return render_html_template(
        request,
        response,
        "reports.html",
        {
            "__REPORT_WORK_ID__": escape(work_id),
            "__REPORT_START_DATE__": escape(start_date),
            "__REPORT_END_DATE__": escape(end_date),
            "__REPORT_STATUS_TEXT__": escape(status_text),
            "__REPORT_STATUS_CLASS__": escape(status_class),
            "__REPORT_STATUS_HIDDEN_ATTR__": status_hidden,
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html(issue_type),
            "__REPORT_STATUS_OPTIONS_HTML__": _report_status_options_html(status),
            "__REPORT_ROWS_HTML__": _report_rows_html(
                reports,
                work_id=work_id,
                issue_type=issue_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
            ),
            "__REPORT_COUNT__": escape(str(len(reports))),
        },
    )
