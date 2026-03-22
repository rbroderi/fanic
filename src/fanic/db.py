from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fanic.paths import DATA_ROOT, DB_PATH, PACKAGE_ROOT, ensure_storage_dirs

SCHEMA_PATH = PACKAGE_ROOT / "sql" / "schema.sql"


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_runtime_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            username TEXT PRIMARY KEY,
            view_explicit_rated INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    if not _table_exists(connection, "works"):
        return

    columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(works)").fetchall()
    }
    if "uploader_username" not in columns:
        connection.execute("ALTER TABLE works ADD COLUMN uploader_username TEXT")
    if "last_metadata_editor" not in columns:
        connection.execute("ALTER TABLE works ADD COLUMN last_metadata_editor TEXT")
    if "last_metadata_edited_at" not in columns:
        connection.execute("ALTER TABLE works ADD COLUMN last_metadata_edited_at TEXT")
    if "last_metadata_edited_by_admin" not in columns:
        connection.execute(
            "ALTER TABLE works ADD COLUMN last_metadata_edited_by_admin INTEGER NOT NULL DEFAULT 0"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS work_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            username TEXT NOT NULL,
            chapter_number INTEGER,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS work_kudos (
            work_id TEXT NOT NULL,
            username TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (work_id, username),
            FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS work_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT NOT NULL,
            chapter_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_page INTEGER NOT NULL,
            end_page INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE,
            UNIQUE (work_id, chapter_index)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS work_chapter_pages (
            chapter_id INTEGER NOT NULL,
            page_image_filename TEXT NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (chapter_id, page_image_filename),
            FOREIGN KEY (chapter_id) REFERENCES work_chapters(id) ON DELETE CASCADE
        )
        """
    )


def get_connection() -> sqlite3.Connection:
    ensure_storage_dirs()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    _ensure_runtime_schema(connection)
    return connection


def _reset_runtime_data() -> None:
    if DATA_ROOT.exists():
        shutil.rmtree(DATA_ROOT)


def initialize_database(
    schema_path: Path = SCHEMA_PATH, *, reset: bool = False
) -> None:
    if reset:
        _reset_runtime_data()
    ensure_storage_dirs()
    sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(sql)
        _ensure_runtime_schema(connection)
