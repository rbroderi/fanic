from collections.abc import Callable
from enum import StrEnum

from fanic.cylinder_sites.report_statuses import ReportStatusType


class ReportsActionMessage(StrEnum):
    REMOVED = "removed"
    MARKED_FALSE = "marked-false"
    MARKED_RESEARCH = "marked-research"
    MARKED_RESOLVED = "marked-resolved"
    MARKED_REOPEN = "marked-reopen"
    PROMOTED_EXPLICIT = "promoted-explicit"
    PROMOTE_MISSING_WORK = "promote-missing-work"
    PROMOTE_WORK_NOT_FOUND = "promote-work-not-found"
    NOT_FOUND = "not-found"
    INVALID_ACTION = "invalid-action"


def run_reports_action_use_case(
    *,
    report_id: int,
    report_action: str,
    report_work_id: str,
    admin_username: str,
    delete_content_report: Callable[[int], bool],
    update_content_report_status: Callable[[int, str], bool],
    set_work_rating: Callable[[str, str], bool],
) -> ReportsActionMessage:
    if report_action == "remove":
        deleted = delete_content_report(report_id)
        return ReportsActionMessage.REMOVED if deleted else ReportsActionMessage.NOT_FOUND

    if report_action == "mark-false":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.FALSE_REPORT.name_to_dash(),
        )
        return ReportsActionMessage.MARKED_FALSE if updated else ReportsActionMessage.NOT_FOUND

    if report_action == "mark-research":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.NEEDS_RESEARCH.name_to_dash(),
        )
        return ReportsActionMessage.MARKED_RESEARCH if updated else ReportsActionMessage.NOT_FOUND

    if report_action == "mark-resolved":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.RESOLVED.name_to_dash(),
        )
        return ReportsActionMessage.MARKED_RESOLVED if updated else ReportsActionMessage.NOT_FOUND

    if report_action == "mark-reopen":
        updated = update_content_report_status(
            report_id,
            ReportStatusType.RE_OPEN.name_to_dash(),
        )
        return ReportsActionMessage.MARKED_REOPEN if updated else ReportsActionMessage.NOT_FOUND

    if report_action == "promote-explicit":
        if not report_work_id:
            return ReportsActionMessage.PROMOTE_MISSING_WORK

        promoted = set_work_rating(report_work_id, admin_username)
        if not promoted:
            return ReportsActionMessage.PROMOTE_WORK_NOT_FOUND

        _ = update_content_report_status(
            report_id,
            ReportStatusType.RESOLVED.name_to_dash(),
        )
        return ReportsActionMessage.PROMOTED_EXPLICIT

    return ReportsActionMessage.INVALID_ACTION
