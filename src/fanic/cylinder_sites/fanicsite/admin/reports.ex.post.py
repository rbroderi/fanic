from urllib.parse import urlencode

from fanic.authorization import AdminReportsPolicy
from fanic.authorization import AuthorizationContext
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.fanicsite.admin.reports_post_service import (
    run_reports_action_use_case,
)
from fanic.repository.social import delete_content_report
from fanic.repository.social import update_content_report_status
from fanic.repository.works import set_work_rating


def _reports_redirect_with_filters(
    response: ResponseLike,
    *,
    msg: str,
    tab: str,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
) -> ResponseLike:
    query: dict[str, str] = {"msg": msg}
    normalized_tab = tab.strip()
    if normalized_tab:
        query["tab"] = normalized_tab
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

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    username = current_user(request)
    user_role = role_for_user(username)
    normalized_username = str(username if username else "")
    reports_ctx = AuthorizationContext.from_inputs(
        current_username=normalized_username,
        current_role=user_role,
    )
    if not AdminReportsPolicy.can_manage(reports_ctx):
        return text_error(response, "Forbidden", 403)
    admin_username = str(username if username else "")

    report_id_raw = request.form.get("report_id", "").strip()
    report_action = request.form.get("report_action", "").strip()
    report_work_id = request.form.get("report_work_id", "").strip()
    tab = request.form.get("tab", "").strip()
    work_id = request.form.get("work_id", "").strip()
    issue_type = request.form.get("issue_type", "").strip()
    status = request.form.get("status", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()

    if not report_id_raw.isdigit():
        return _reports_redirect_with_filters(
            response,
            msg="invalid-id",
            tab=tab,
            work_id=work_id,
            issue_type=issue_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )

    report_id = int(report_id_raw)

    def set_work_rating_for_promote(work_id: str, editor_username: str) -> bool:
        return set_work_rating(
            work_id,
            "Explicit",
            editor_username=editor_username,
            edited_by_admin=True,
        )

    action_msg = run_reports_action_use_case(
        report_id=report_id,
        report_action=report_action,
        report_work_id=report_work_id,
        admin_username=admin_username,
        delete_content_report=delete_content_report,
        update_content_report_status=update_content_report_status,
        set_work_rating=set_work_rating_for_promote,
    )

    return _reports_redirect_with_filters(
        response,
        msg=str(action_msg),
        tab=tab,
        work_id=work_id,
        issue_type=issue_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
