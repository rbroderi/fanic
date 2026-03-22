from __future__ import annotations

from urllib.parse import urlencode

from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.report_statuses import ReportStatusType
from fanic.repository import delete_content_report
from fanic.repository import set_work_rating
from fanic.repository import update_content_report_status


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _reports_redirect_with_filters(
    response: ResponseLike,
    *,
    msg: str,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
) -> ResponseLike:
    query: dict[str, str] = {"msg": msg}
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
    return _redirect(response, f"/admin/reports?{urlencode(query)}")


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/reports":
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request):
        return text_error(response, "HTTPS required", 400)

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    username = current_user(request)
    if role_for_user(username) not in {"superadmin", "admin"}:
        return text_error(response, "Forbidden", 403)
    admin_username = str(username if username else "")

    report_id_raw = request.form.get("report_id", "").strip()
    report_action = request.form.get("report_action", "").strip()
    report_work_id = request.form.get("report_work_id", "").strip()
    work_id = request.form.get("work_id", "").strip()
    issue_type = request.form.get("issue_type", "").strip()
    status = request.form.get("status", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if not report_id_raw.isdigit():
        return _reports_redirect_with_filters(
            response,
            msg="invalid-id",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    report_id = int(report_id_raw)

    if report_action == "remove":
        deleted = delete_content_report(report_id)
        return _reports_redirect_with_filters(
            response,
            msg="removed" if deleted else "not-found",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    if report_action == "mark-false":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.FALSE_REPORT.name_to_dash(),
        )
        return _reports_redirect_with_filters(
            response,
            msg="marked-false" if updated else "not-found",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    if report_action == "mark-research":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.NEEDS_RESEARCH.name_to_dash(),
        )
        return _reports_redirect_with_filters(
            response,
            msg="marked-research" if updated else "not-found",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    if report_action == "mark-resolved":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.RESOLVED.name_to_dash(),
        )
        return _reports_redirect_with_filters(
            response,
            msg="marked-resolved" if updated else "not-found",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    if report_action == "mark-reopen":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.RE_OPEN.name_to_dash(),
        )
        return _reports_redirect_with_filters(
            response,
            msg="marked-reopen" if updated else "not-found",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    if report_action == "promote-explicit":
        if not report_work_id:
            return _reports_redirect_with_filters(
                response,
                msg="promote-missing-work",
                work_id=work_id,
                issue_type=issue_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
            )

        promoted = set_work_rating(
            report_work_id,
            "Explicit",
            editor_username=admin_username,
            edited_by_admin=True,
        )
        if not promoted:
            return _reports_redirect_with_filters(
                response,
                msg="promote-work-not-found",
                work_id=work_id,
                issue_type=issue_type,
                status=status,
                start_date=start_date,
                end_date=end_date,
            )

        _ = update_content_report_status(
            report_id,
            ReportStatusType.RESOLVED.name_to_dash(),
        )
        return _reports_redirect_with_filters(
            response,
            msg="promoted-explicit",
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    return _reports_redirect_with_filters(
        response,
        msg="invalid-action",
        work_id=work_id,
        issue_type=issue_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
