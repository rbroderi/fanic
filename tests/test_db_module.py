from __future__ import annotations

import sqlite3
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

import fanic.db as db


def _table_exists_fn() -> Callable[[sqlite3.Connection, str], bool]:
    return cast(Callable[[sqlite3.Connection, str], bool], getattr(db, "_table_exists"))


def _ensure_runtime_schema_fn() -> Callable[[sqlite3.Connection], None]:
    return cast(
        Callable[[sqlite3.Connection], None], getattr(db, "_ensure_runtime_schema")
    )


def test_managed_connection_closes_on_context_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "ensure_storage_dirs", lambda: None)

    connection = db.get_connection()
    with connection as active:
        active.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_table_exists_helper_detects_existing_and_missing_tables() -> None:
    table_exists = _table_exists_fn()
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE demo (id INTEGER)")
        assert table_exists(connection, "demo") is True
        assert table_exists(connection, "missing") is False
    finally:
        connection.close()


def test_ensure_runtime_schema_adds_missing_user_preference_columns() -> None:
    ensure_runtime_schema = _ensure_runtime_schema_fn()
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            """
            CREATE TABLE user_preferences (
                username TEXT PRIMARY KEY,
                view_explicit_rated INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_runtime_schema(connection)

        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(user_preferences)"
            ).fetchall()
        }
        assert "custom_theme_enabled" in columns
        assert "custom_theme_toml" in columns
    finally:
        connection.close()


def test_ensure_runtime_schema_backfills_works_columns_and_tables() -> None:
    ensure_runtime_schema = _ensure_runtime_schema_fn()
    table_exists = _table_exists_fn()
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE user_preferences (username TEXT PRIMARY KEY)")
        connection.execute(
            """
            CREATE TABLE works (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )

        ensure_runtime_schema(connection)

        work_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(works)").fetchall()
        }
        assert "uploader_username" in work_columns
        assert "last_metadata_editor" in work_columns
        assert "last_metadata_edited_at" in work_columns
        assert "last_metadata_edited_by_admin" in work_columns

        assert table_exists(connection, "work_comments") is True
        assert table_exists(connection, "work_kudos") is True
        assert table_exists(connection, "work_chapters") is True
        assert table_exists(connection, "work_chapter_pages") is True
    finally:
        connection.close()


def test_initialize_database_reset_recreates_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "fanic.sqlite3"

    schema_path = (
        Path(__file__).resolve().parents[1] / "src" / "fanic" / "sql" / "schema.sql"
    )

    monkeypatch.setattr(db, "DATA_ROOT", data_root)
    monkeypatch.setattr(db, "DB_PATH", db_path)

    def fake_ensure_storage_dirs() -> None:
        data_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db, "ensure_storage_dirs", fake_ensure_storage_dirs)

    data_root.mkdir(parents=True, exist_ok=True)
    marker = data_root / "marker.txt"
    marker.write_text("old", encoding="utf-8")

    db.initialize_database(schema_path=schema_path, reset=True)

    assert db_path.exists() is True
    assert marker.exists() is False

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert "works" in tables
    assert "user_preferences" in tables


def test_create_runtime_backup_archives_db_and_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "fanic.db"
    cbz_dir = data_root / "cbz"
    works_dir = data_root / "works"

    monkeypatch.setattr(db, "DATA_ROOT", data_root)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "CBZ_DIR", cbz_dir)
    monkeypatch.setattr(db, "WORKS_DIR", works_dir)

    def fake_ensure_storage_dirs() -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        cbz_dir.mkdir(parents=True, exist_ok=True)
        works_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db, "ensure_storage_dirs", fake_ensure_storage_dirs)

    fake_ensure_storage_dirs()
    db_path.write_text("sqlite-bytes", encoding="utf-8")
    (cbz_dir / "work-1.cbz").write_text("cbz", encoding="utf-8")
    page = works_dir / "work-1" / "pages" / "001.jpg"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("jpg", encoding="utf-8")

    backup_path = tmp_path / "backup.zip"
    created_path = db.create_runtime_backup(backup_path)

    assert created_path == backup_path.resolve()
    with zipfile.ZipFile(created_path, mode="r") as archive:
        names = set(archive.namelist())
    assert "fanic.db" in names
    assert "cbz/work-1.cbz" in names
    assert "works/work-1/pages/001.jpg" in names


def test_restore_runtime_backup_requires_force_when_data_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "fanic.db"
    cbz_dir = data_root / "cbz"
    works_dir = data_root / "works"

    monkeypatch.setattr(db, "DATA_ROOT", data_root)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "CBZ_DIR", cbz_dir)
    monkeypatch.setattr(db, "WORKS_DIR", works_dir)

    def fake_ensure_storage_dirs() -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        cbz_dir.mkdir(parents=True, exist_ok=True)
        works_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db, "ensure_storage_dirs", fake_ensure_storage_dirs)

    fake_ensure_storage_dirs()
    (data_root / "existing.txt").write_text("existing", encoding="utf-8")

    backup_path = tmp_path / "restore-source.zip"
    with zipfile.ZipFile(
        backup_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("fanic.db", "newdb")

    with pytest.raises(FileExistsError):
        db.restore_runtime_backup(backup_path, force=False)


def test_restore_runtime_backup_replaces_runtime_data_when_forced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    db_path = data_root / "fanic.db"
    cbz_dir = data_root / "cbz"
    works_dir = data_root / "works"

    monkeypatch.setattr(db, "DATA_ROOT", data_root)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "CBZ_DIR", cbz_dir)
    monkeypatch.setattr(db, "WORKS_DIR", works_dir)

    def fake_ensure_storage_dirs() -> None:
        data_root.mkdir(parents=True, exist_ok=True)
        cbz_dir.mkdir(parents=True, exist_ok=True)
        works_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db, "ensure_storage_dirs", fake_ensure_storage_dirs)

    fake_ensure_storage_dirs()
    db_path.write_text("old-db", encoding="utf-8")
    (cbz_dir / "old.cbz").write_text("old", encoding="utf-8")

    backup_path = tmp_path / "restore-source.zip"
    with zipfile.ZipFile(
        backup_path, mode="w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("fanic.db", "new-db")
        archive.writestr("cbz/new.cbz", "new-cbz")
        archive.writestr("works/work-2/pages/001.jpg", "img")

    db.restore_runtime_backup(backup_path, force=True)

    assert db_path.read_text(encoding="utf-8") == "new-db"
    assert (cbz_dir / "new.cbz").exists() is True
    assert (cbz_dir / "old.cbz").exists() is False
    assert (works_dir / "work-2" / "pages" / "001.jpg").exists() is True
