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


def _report_rows_html(reports: list[ContentReportRow]) -> str:
    if not reports:
        return '<p class="profile-meta">No reports found for the selected filters.</p>'

    rows: list[str] = []
    for report in reports:
        report_id = escape(str(report["id"]))
        created_at = escape(report["created_at"])
        issue_type = escape(report["issue_type"])
        issue_label = escape(report_issue_label(report["issue_type"]))
        work_id_raw = report["work_id"]
        work_id = escape(work_id_raw) if work_id_raw is not None else ""
        work_title = escape(report["work_title"] if report["work_title"] else "")
        reporter_name = escape(report["reporter_name"])
        reporter_email = escape(report["reporter_email"])
        claimed_url = escape(report["claimed_url"])
        evidence_url = escape(report["evidence_url"])
        details = escape(report["details"]).replace("\n", "<br />")
        reporter_username = escape(report["reporter_username"])

        work_display = (
            f"{work_title} ({work_id})"
            if work_title and work_id
            else (work_title if work_title else (work_id if work_id else "-"))
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
            + f"<p><strong>Work:</strong> {work_display}</p>"
            + f"<p><strong>Reporter:</strong> {reporter_display} | {reporter_email}</p>"
            + f'<p><strong>Claimed URL:</strong> <a href="{claimed_url}" target="_blank" rel="noopener noreferrer">{claimed_url}</a></p>'
            + f"<p><strong>Evidence:</strong> {evidence_html}</p>"
            + f"<p><strong>Details:</strong><br />{details}</p>"
            + "</article>"
        )
    return "".join(rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/reports":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if username != ADMIN_USERNAME:
        return text_error(response, "Forbidden", 403)

    work_id = request.args.get("work_id", "").strip()
    issue_type = request.args.get("issue_type", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    reports = list_content_reports(
        work_id=work_id,
        issue_type=issue_type,
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
            "__REPORT_ISSUE_OPTIONS_HTML__": report_issue_options_html(issue_type),
            "__REPORT_ROWS_HTML__": _report_rows_html(reports),
            "__REPORT_COUNT__": escape(str(len(reports))),
        },
    )
