from dataclasses import dataclass
from html import escape
from textwrap import dedent
from urllib.parse import urlencode

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.feedback_categories import feedback_category_label
from fanic.cylinder_sites.feedback_categories import feedback_category_options_html
from fanic.cylinder_sites.report_issues import report_issue_label
from fanic.cylinder_sites.report_issues import report_issue_options_html
from fanic.cylinder_sites.report_statuses import report_status_label
from fanic.cylinder_sites.report_statuses import report_status_options_html
from fanic.repository import ContentReportRow
from fanic.repository import list_content_reports


@dataclass(frozen=True, slots=True)
class StatusReplacements:
    text: str
    css_class: str
    hidden_attr: str


def _report_tab(tab: str) -> str:
    normalized = tab.strip().lower()
    return normalized if normalized in {"content", "feedback"} else "content"


def _source_path_for_tab(tab: str) -> str:
    return "/feedback" if tab == "feedback" else "/dmca"


def _tab_filter_href(
    tab: str,
    *,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
) -> str:
    query: dict[str, str] = {"tab": tab}
    if work_id:
        query["work_id"] = work_id
    if issue_type:
        query["issue_type"] = issue_type
    if status:
        query["status"] = status
    if start_date:
        query["start_date"] = start_date
    if end_date:
        query["end_date"] = end_date
    return f"/admin/reports?{urlencode(query)}"


def _status_replacements(msg: str) -> StatusReplacements:
    match msg:
        case "removed":
            return StatusReplacements("Report removed.", "success", "")
        case "marked-false":
            return StatusReplacements("Report marked as false report.", "success", "")
        case "marked-research":
            return StatusReplacements(
                "Report marked as more research needed.",
                "success",
                "",
            )
        case "marked-resolved":
            return StatusReplacements("Report marked as resolved.", "success", "")
        case "marked-reopen":
            return StatusReplacements("Report marked as re-open.", "success", "")
        case "promoted-explicit":
            return StatusReplacements(
                "Work rating promoted to Explicit and report marked resolved.",
                "success",
                "",
            )
        case "promote-missing-work":
            return StatusReplacements(
                "Cannot promote rating: report is not linked to a work id.",
                "error",
                "",
            )
        case "promote-work-not-found":
            return StatusReplacements(
                "Cannot promote rating: linked work was not found.",
                "error",
                "",
            )
        case "not-found":
            return StatusReplacements("Report not found.", "error", "")
        case "invalid-id":
            return StatusReplacements("Invalid report id.", "error", "")
        case "invalid-action":
            return StatusReplacements("Invalid report action.", "error", "")
        case _:
            return StatusReplacements("", "", "hidden")


def _report_rows_html(
    reports: list[ContentReportRow],
    *,
    tab: str,
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
        issue_label = escape(
            feedback_category_label(report["issue_type"])
            if tab == "feedback"
            else report_issue_label(report["issue_type"])
        )
        report_status_raw = report["status"]
        report_status = escape(report_status_raw)
        report_status_label_text = escape(report_status_label(report_status_raw))
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
            else (work_title if work_title else (report_work_id if report_work_id else "-"))
        )
        reporter_display = f"{reporter_name} ({reporter_username})" if reporter_username else reporter_name

        evidence_html = (
            f'<a href="{evidence_url}" target="_blank" rel="noopener noreferrer">Evidence</a>' if evidence_url else "-"
        )

        promote_button_html = (
            '<button type="submit" name="report_action" value="promote-explicit" class="button-muted">Promote to explicit rating</button>'
            if tab == "content"
            else ""
        )

        rows.append(
            dedent(
                f"""\
                <article class="card comment-card">
                <p class="comment-meta"><strong>Report #{report_id}</strong> | {created_at}</p>
                <p><strong>Type:</strong> {issue_label} <span class="profile-meta">({issue_type})</span></p>
                <p><strong>Status:</strong> {report_status_label_text} <span class="profile-meta">({report_status})</span></p>
                <p><strong>Work:</strong> {work_display}</p>
                <p><strong>Reporter:</strong> {reporter_display} | {reporter_email}</p>
                <p><strong>Claimed URL:</strong> <a href="{claimed_url}" target="_blank" rel="noopener noreferrer">{claimed_url}</a></p>
                <p><strong>Evidence:</strong> {evidence_html}</p>
                <p><strong>Details:</strong><br />{details}</p>
                <form class="upload-form" method="post" action="/admin/reports" style="margin-top:0.75rem;">
                <input type="hidden" name="report_id" value="{report_id}" />
                <input type="hidden" name="report_work_id" value="{report_work_id}" />
                <input type="hidden" name="work_id" value="{escape(filter_work_id)}" />
                <input type="hidden" name="issue_type" value="{escape(filter_issue_type)}" />
                <input type="hidden" name="status" value="{escape(filter_status)}" />
                <input type="hidden" name="start_date" value="{escape(filter_start_date)}" />
                <input type="hidden" name="end_date" value="{escape(filter_end_date)}" />
                <input type="hidden" name="tab" value="{escape(tab)}" />
                <button type="submit" name="report_action" value="mark-resolved" class="button-muted">Mark resolved</button>
                <button type="submit" name="report_action" value="mark-reopen" class="button-muted">Mark re-open</button>
                <button type="submit" name="report_action" value="mark-false" class="button-muted">Mark false</button>
                <button type="submit" name="report_action" value="mark-research" class="button-muted">Mark more research needed</button>
                {promote_button_html}
                <button type="submit" name="report_action" value="remove" class="button-danger" onclick="return confirm('Remove this report item?');">Remove item</button>
                </form>
                </article>
                """
            ).strip()
        )
    return "".join(rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/reports":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if role_for_user(username) not in {"superadmin", "admin"}:
        return text_error(response, "Forbidden", 403)

    msg = request.args.get("msg", "").strip()
    tab = _report_tab(request.args.get("tab", "content"))
    work_id = request.args.get("work_id", "").strip()
    issue_type = request.args.get("issue_type", "").strip()
    status = request.args.get("status", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    status_replacements = _status_replacements(msg)

    report_kwargs: dict[str, str] = {
        "work_id": work_id,
        "issue_type": issue_type,
        "status": status,
        "start_date": start_date,
        "end_date": end_date,
    }
    source_path = _source_path_for_tab(tab)
    reports: list[ContentReportRow]
    try:
        reports = list_content_reports(
            **report_kwargs,
            source_path=source_path,
        )
    except TypeError:
        reports = list_content_reports(**report_kwargs)

    issue_options_html = (
        feedback_category_options_html(issue_type) if tab == "feedback" else report_issue_options_html(issue_type)
    )
    issue_filter_label = "Feedback category" if tab == "feedback" else "Issue type"
    work_filter_hidden_attr = "hidden" if tab == "feedback" else ""

    tab_content_href = _tab_filter_href(
        "content",
        work_id=work_id,
        issue_type=issue_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    tab_feedback_href = _tab_filter_href(
        "feedback",
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
            "__REPORT_TAB__": escape(tab),
            "__REPORT_TAB_CONTENT_HREF__": tab_content_href,
            "__REPORT_TAB_FEEDBACK_HREF__": tab_feedback_href,
            "__REPORT_TAB_CONTENT_ACTIVE__": ('aria-current="page"' if tab == "content" else ""),
            "__REPORT_TAB_FEEDBACK_ACTIVE__": ('aria-current="page"' if tab == "feedback" else ""),
            "__REPORT_TITLE__": ("Feedback Queue" if tab == "feedback" else "Submitted Reports"),
            "__REPORT_WORK_ID__": escape(work_id),
            "__REPORT_WORK_FILTER_HIDDEN_ATTR__": work_filter_hidden_attr,
            "__REPORT_WORK_INPUT_HIDDEN_ATTR__": work_filter_hidden_attr,
            "__REPORT_START_DATE__": escape(start_date),
            "__REPORT_END_DATE__": escape(end_date),
            "__REPORT_STATUS_TEXT__": escape(status_replacements.text),
            "__REPORT_STATUS_CLASS__": escape(status_replacements.css_class),
            "__REPORT_STATUS_HIDDEN_ATTR__": status_replacements.hidden_attr,
            "__REPORT_ISSUE_FILTER_LABEL__": escape(issue_filter_label),
            "__REPORT_ISSUE_OPTIONS_HTML__": issue_options_html,
            "__REPORT_STATUS_OPTIONS_HTML__": report_status_options_html(status),
            "__REPORT_ROWS_HTML__": _report_rows_html(
                reports,
                tab=tab,
                work_id=work_id,
                issue_type=issue_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
            ),
            "__REPORT_COUNT__": escape(str(len(reports))),
        },
    )
