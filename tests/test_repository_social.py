import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Literal
from typing import override

import pytest

import fanic.repository.social as social


class _ManagedTestConnection(sqlite3.Connection):
    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
        return False


def _setup_social_db(db_path: Path) -> None:
    with sqlite3.connect(db_path, factory=_ManagedTestConnection) as connection:
        connection.execute(
            """
            CREATE TABLE dmca_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_id TEXT,
                work_title TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                reason TEXT NOT NULL,
                reporter_name TEXT NOT NULL,
                reporter_email TEXT NOT NULL,
                claimed_url TEXT NOT NULL,
                evidence_url TEXT NOT NULL,
                details TEXT NOT NULL,
                reporter_username TEXT,
                source_path TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def test_add_dmca_report_stores_blank_work_id_as_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "social.sqlite3"
    _setup_social_db(db_path)

    def get_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=_ManagedTestConnection)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(social, "get_connection", get_connection)

    report_id = social.add_dmca_report(
        work_id="   ",
        work_title="Untitled",
        issue_type="dmca",
        reporter_name="Alice",
        reporter_email="alice@example.com",
        reason="Infringement",
        claimed_url="https://example.com/work",
        evidence_url="https://example.com/evidence",
        details="details",
        reporter_username="alice",
        source_path="/reports",
    )

    assert report_id > 0
    with sqlite3.connect(db_path, factory=_ManagedTestConnection) as connection:
        row = connection.execute(
            "SELECT work_id FROM dmca_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
    assert row is not None
    assert row[0] is None


def test_list_content_reports_applies_filters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "social.sqlite3"
    _setup_social_db(db_path)

    def get_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=_ManagedTestConnection)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(social, "get_connection", get_connection)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO dmca_reports (
                work_id, work_title, issue_type, status, reason,
                reporter_name, reporter_email, claimed_url, evidence_url,
                details, reporter_username, source_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "work-1",
                "One",
                "dmca",
                "open",
                "reason-a",
                "Alice",
                "alice@example.com",
                "https://example.com/one",
                "https://example.com/evidence-one",
                "details-a",
                "alice",
                "mod-queue",
                "2026-03-01 10:00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO dmca_reports (
                work_id, work_title, issue_type, status, reason,
                reporter_name, reporter_email, claimed_url, evidence_url,
                details, reporter_username, source_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "work-2",
                "Two",
                "dmca",
                "resolved",
                "reason-b",
                "Bob",
                "bob@example.com",
                "https://example.com/two",
                "https://example.com/evidence-two",
                "details-b",
                None,
                "mod-queue",
                "2026-03-02 10:00:00",
            ),
        )

    filtered = social.list_content_reports(
        work_id="work-2",
        issue_type="dmca",
        status="resolved",
        start_date="2026-03-02",
        end_date="2026-03-31",
        source_path="mod-queue",
        limit=10,
    )

    assert len(filtered) == 1
    assert filtered[0]["work_id"] == "work-2"
    assert filtered[0]["status"] == "resolved"
    assert filtered[0]["reporter_username"] == ""


def test_update_and_delete_content_report_return_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "social.sqlite3"
    _setup_social_db(db_path)

    def get_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=_ManagedTestConnection)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(social, "get_connection", get_connection)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dmca_reports (
                work_id, work_title, issue_type, status, reason,
                reporter_name, reporter_email, claimed_url, evidence_url,
                details, reporter_username, source_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "work-1",
                "One",
                "dmca",
                "open",
                "reason",
                "Alice",
                "alice@example.com",
                "https://example.com/one",
                "https://example.com/evidence",
                "details",
                "alice",
                "mod-queue",
            ),
        )
        report_id_raw = cursor.lastrowid

    assert report_id_raw is not None
    report_id = int(report_id_raw)

    assert social.update_content_report_status(report_id, "resolved") is True
    assert social.update_content_report_status(9999, "resolved") is False

    assert social.delete_content_report(report_id) is True
    assert social.delete_content_report(report_id) is False
