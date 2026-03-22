from __future__ import annotations

import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from types import TracebackType
from typing import Literal
from typing import override

from fanic.settings import CBZ_DIR
from fanic.settings import DATA_ROOT
from fanic.settings import DB_PATH
from fanic.settings import WORKS_DIR
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

_SETTINGS = get_settings()
SCHEMA_PATH = _SETTINGS.package_root / "sql" / "schema.sql"


class _ManagedConnection(sqlite3.Connection):
    """Connection that closes itself when exiting a context manager."""

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


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_runtime_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            email TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    user_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(users)").fetchall()
    }
    if "username" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN username TEXT NOT NULL DEFAULT ''"
        )
    if "display_name" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''"
        )
    if "email" not in user_columns:
        connection.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if "active" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
        )
    if "role" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
        )
    if "created_at" not in user_columns:
        connection.execute(
            "ALTER TABLE users ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
        )
    admin_username = _SETTINGS.admin_username.strip()
    if admin_username:
        connection.execute(
            """
            INSERT INTO users (id, username, display_name, email, active, role)
            VALUES (?, ?, ?, NULL, 1, 'superadmin')
            ON CONFLICT(username) DO UPDATE SET
                active = 1,
                role = 'superadmin'
            """,
            (
                admin_username,
                admin_username,
                admin_username,
            ),
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            username TEXT PRIMARY KEY,
            view_explicit_rated INTEGER NOT NULL DEFAULT 0,
            custom_theme_enabled INTEGER NOT NULL DEFAULT 0,
            custom_theme_toml TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    preference_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(user_preferences)").fetchall()
    }
    if "custom_theme_enabled" not in preference_columns:
        connection.execute(
            "ALTER TABLE user_preferences ADD COLUMN custom_theme_enabled INTEGER NOT NULL DEFAULT 0"
        )
    if "custom_theme_toml" not in preference_columns:
        connection.execute(
            "ALTER TABLE user_preferences ADD COLUMN custom_theme_toml TEXT"
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dmca_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id TEXT,
            work_title TEXT NOT NULL DEFAULT '',
            issue_type TEXT NOT NULL DEFAULT 'copyright-dmca',
            status TEXT NOT NULL DEFAULT 'open',
            reporter_name TEXT NOT NULL,
            reporter_email TEXT NOT NULL,
            reason TEXT NOT NULL,
            claimed_url TEXT NOT NULL,
            evidence_url TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL,
            reporter_username TEXT,
            source_path TEXT NOT NULL DEFAULT '/dmca',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    dmca_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(dmca_reports)").fetchall()
    }
    if "issue_type" not in dmca_columns:
        connection.execute(
            "ALTER TABLE dmca_reports ADD COLUMN issue_type TEXT NOT NULL DEFAULT 'copyright-dmca'"
        )
    if "status" not in dmca_columns:
        connection.execute(
            "ALTER TABLE dmca_reports ADD COLUMN status TEXT NOT NULL DEFAULT 'open'"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_dmca_reports_status ON dmca_reports(status)"
    )


def get_connection() -> sqlite3.Connection:
    ensure_storage_dirs()
    connection = sqlite3.connect(DB_PATH, factory=_ManagedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    _ensure_runtime_schema(connection)
    return connection


def _reset_runtime_data() -> None:
    if DATA_ROOT.exists():
        shutil.rmtree(DATA_ROOT)


def initialize_database(schema_path: Path = SCHEMA_PATH, *, reset: bool = False) -> int:
    if reset:
        _reset_runtime_data()
    ensure_storage_dirs()
    sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH, factory=_ManagedConnection) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(sql)
        _ensure_runtime_schema(connection)
    return 0


def create_runtime_backup(backup_path: Path) -> Path:
    ensure_storage_dirs()
    resolved_backup_path = backup_path.expanduser().resolve()
    if resolved_backup_path.suffix.lower() != ".zip":
        raise ValueError("Backup path must end with .zip")
    if resolved_backup_path.exists():
        raise FileExistsError(f"Backup already exists: {resolved_backup_path}")

    resolved_backup_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        resolved_backup_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        if DB_PATH.exists():
            archive.write(DB_PATH, arcname=DB_PATH.name)
        for runtime_dir in (CBZ_DIR, WORKS_DIR):
            if not runtime_dir.exists():
                continue
            for file_path in sorted(runtime_dir.rglob("*")):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(DATA_ROOT)).replace("\\", "/")
                    archive.write(file_path, arcname=arcname)
    return resolved_backup_path


def _safe_extract_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()

    for info in archive.infolist():
        member_path = (destination_resolved / info.filename).resolve()
        if not member_path.is_relative_to(destination_resolved):
            raise ValueError(f"Archive contains unsafe path: {info.filename}")
        archive.extract(info, destination_resolved)


def restore_runtime_backup(backup_path: Path, *, force: bool = False) -> int:
    resolved_backup_path = backup_path.expanduser().resolve()
    if not resolved_backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {resolved_backup_path}")
    if resolved_backup_path.suffix.lower() != ".zip":
        raise ValueError("Backup path must end with .zip")

    if DATA_ROOT.exists() and any(DATA_ROOT.iterdir()):
        if not force:
            raise FileExistsError(
                "Data directory is not empty. Re-run with force=True to overwrite it."
            )
        shutil.rmtree(DATA_ROOT)

    with tempfile.TemporaryDirectory(prefix="fanic-restore-") as tmp_dir:
        extract_root = Path(tmp_dir) / "extract"
        with zipfile.ZipFile(resolved_backup_path, mode="r") as archive:
            member_names = {info.filename.strip("/") for info in archive.infolist()}
            _safe_extract_zip(archive, extract_root)

        has_runtime_payload = any(
            name == "fanic.db" or name.startswith("cbz/") or name.startswith("works/")
            for name in member_names
        )
        if not has_runtime_payload:
            raise ValueError("Backup archive does not contain FANIC runtime data")

        ensure_storage_dirs()
        restored_db = extract_root / DB_PATH.name
        if restored_db.exists():
            shutil.copy2(restored_db, DB_PATH)

        for source_name, destination_dir in (("cbz", CBZ_DIR), ("works", WORKS_DIR)):
            source_dir = extract_root / source_name
            if destination_dir.exists():
                shutil.rmtree(destination_dir)
            if source_dir.exists():
                shutil.copytree(source_dir, destination_dir)
            else:
                destination_dir.mkdir(parents=True, exist_ok=True)
    return 0
