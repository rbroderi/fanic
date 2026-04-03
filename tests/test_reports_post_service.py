from fanic.cylinder_sites.fanicsite.admin.reports_post_service import (
    ReportsActionMessage,
)
from fanic.cylinder_sites.fanicsite.admin.reports_post_service import (
    run_reports_action_use_case,
)


def test_reports_action_remove_not_found() -> None:
    msg = run_reports_action_use_case(
        report_id=7,
        report_action="remove",
        report_work_id="",
        admin_username="admin",
        delete_content_report=lambda _report_id: False,
        update_content_report_status=lambda _report_id, _status: True,
        set_work_rating=lambda _work_id, _admin_username: True,
    )
    assert msg == ReportsActionMessage.NOT_FOUND


def test_reports_action_mark_false() -> None:
    captured: dict[str, object] = {}

    def update_status(report_id: int, status: str) -> bool:
        captured["report_id"] = report_id
        captured["status"] = status
        return True

    msg = run_reports_action_use_case(
        report_id=22,
        report_action="mark-false",
        report_work_id="",
        admin_username="admin",
        delete_content_report=lambda _report_id: True,
        update_content_report_status=update_status,
        set_work_rating=lambda _work_id, _admin_username: True,
    )
    assert msg == ReportsActionMessage.MARKED_FALSE
    assert captured == {"report_id": 22, "status": "false-report"}


def test_reports_action_promote_explicit_paths() -> None:
    statuses: list[str] = []
    calls: list[tuple[str, str]] = []

    def update_status(_report_id: int, status: str) -> bool:
        statuses.append(status)
        return True

    def set_rating(work_id: str, admin_username: str) -> bool:
        calls.append((work_id, admin_username))
        return True

    msg = run_reports_action_use_case(
        report_id=11,
        report_action="promote-explicit",
        report_work_id="work-11",
        admin_username="admin",
        delete_content_report=lambda _report_id: True,
        update_content_report_status=update_status,
        set_work_rating=set_rating,
    )

    assert msg == ReportsActionMessage.PROMOTED_EXPLICIT
    assert calls == [("work-11", "admin")]
    assert statuses == ["resolved"]

    missing_msg = run_reports_action_use_case(
        report_id=11,
        report_action="promote-explicit",
        report_work_id="",
        admin_username="admin",
        delete_content_report=lambda _report_id: True,
        update_content_report_status=update_status,
        set_work_rating=set_rating,
    )
    assert missing_msg == ReportsActionMessage.PROMOTE_MISSING_WORK
