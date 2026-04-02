"""social repository domain implementation."""

from typing import TypedDict

from fanic.db import get_connection


class ContentReportRow(TypedDict):
    id: int
    work_id: str | None
    work_title: str
    issue_type: str
    status: str
    reason: str
    reporter_name: str
    reporter_email: str
    claimed_url: str
    evidence_url: str
    details: str
    reporter_username: str
    source_path: str
    created_at: str


def add_dmca_report(
    *,
    work_id: str | None,
    work_title: str,
    issue_type: str,
    reporter_name: str,
    reporter_email: str,
    reason: str,
    claimed_url: str,
    evidence_url: str,
    details: str,
    reporter_username: str | None,
    source_path: str,
) -> int:
    normalized_work_id = work_id.strip() if work_id else ""
    stored_work_id = normalized_work_id if normalized_work_id else None
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dmca_reports (
                work_id,
                work_title,
                issue_type,
                reporter_name,
                reporter_email,
                reason,
                claimed_url,
                evidence_url,
                details,
                reporter_username,
                source_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored_work_id,
                work_title,
                issue_type,
                reporter_name,
                reporter_email,
                reason,
                claimed_url,
                evidence_url,
                details,
                reporter_username,
                source_path,
            ),
        )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to persist DMCA report")
    return int(cursor.lastrowid)


def list_content_reports(
    *,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
    source_path: str,
    limit: int = 250,
) -> list[ContentReportRow]:
    where: list[str] = []
    params: list[object] = []

    normalized_work_id = work_id.strip()
    if normalized_work_id:
        where.append("work_id = ?")
        params.append(normalized_work_id)

    normalized_issue_type = issue_type.strip()
    if normalized_issue_type:
        where.append("issue_type = ?")
        params.append(normalized_issue_type)

    normalized_status = status.strip()
    if normalized_status:
        where.append("status = ?")
        params.append(normalized_status)

    normalized_start_date = start_date.strip()
    if normalized_start_date:
        where.append("substr(created_at, 1, 10) >= ?")
        params.append(normalized_start_date)

    normalized_end_date = end_date.strip()
    if normalized_end_date:
        where.append("substr(created_at, 1, 10) <= ?")
        params.append(normalized_end_date)

    normalized_source_path = source_path.strip()
    if normalized_source_path:
        where.append("source_path = ?")
        params.append(normalized_source_path)

    sql = """
        SELECT
            id,
            work_id,
            work_title,
            issue_type,
            status,
            reason,
            reporter_name,
            reporter_email,
            claimed_url,
            evidence_url,
            details,
            reporter_username,
            source_path,
            created_at
        FROM dmca_reports
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    reports: list[ContentReportRow] = []
    for row in rows:
        work_id_obj = row["work_id"]
        reporter_username_obj = row["reporter_username"]
        reports.append(
            {
                "id": int(row["id"]),
                "work_id": str(work_id_obj) if work_id_obj is not None else None,
                "work_title": str(row["work_title"]),
                "issue_type": str(row["issue_type"]),
                "status": str(row["status"]),
                "reason": str(row["reason"]),
                "reporter_name": str(row["reporter_name"]),
                "reporter_email": str(row["reporter_email"]),
                "claimed_url": str(row["claimed_url"]),
                "evidence_url": str(row["evidence_url"]),
                "details": str(row["details"]),
                "reporter_username": (str(reporter_username_obj) if reporter_username_obj is not None else ""),
                "source_path": str(row["source_path"]),
                "created_at": str(row["created_at"]),
            }
        )
    return reports


def update_content_report_status(report_id: int, status: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE dmca_reports
            SET status = ?
            WHERE id = ?
            """,
            (status, report_id),
        )
    return cursor.rowcount > 0


def delete_content_report(report_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM dmca_reports WHERE id = ?",
            (report_id,),
        )
    return cursor.rowcount > 0
