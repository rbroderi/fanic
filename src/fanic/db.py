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
from fanic.settings import FANART_DIR
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
    if not _table_exists(connection, "users"):
        return

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_identities (
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            username TEXT NOT NULL,
            email TEXT,
            email_verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (provider, subject),
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_identities_username
        ON auth_identities(username)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_identities_email
        ON auth_identities(email)
        """
    )


def get_connection() -> sqlite3.Connection:
    ensure_storage_dirs()
    connection = sqlite3.connect(DB_PATH, factory=_ManagedConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    connection.execute("PRAGMA busy_timeout = 5000;")
    _ensure_runtime_schema(connection)
    return connection


def _reset_runtime_data() -> None:
    if DATA_ROOT.exists():
        for child in DATA_ROOT.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

    if DB_PATH.exists() and DB_PATH.parent != DATA_ROOT:
        DB_PATH.unlink()


def initialize_database(schema_path: Path = SCHEMA_PATH, *, reset: bool = False) -> int:
    if reset:
        _reset_runtime_data()
    ensure_storage_dirs()
    sql = schema_path.read_text(encoding="utf-8")
    with sqlite3.connect(DB_PATH, factory=_ManagedConnection) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA synchronous = NORMAL;")
        connection.execute("PRAGMA busy_timeout = 5000;")
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
        for runtime_dir in (CBZ_DIR, WORKS_DIR, FANART_DIR):
            if not runtime_dir.exists():
                continue
            for file_path in sorted(runtime_dir.rglob("*")):
                if file_path.is_file():
                    relative_path = file_path.relative_to(runtime_dir)
                    arcname = f"{runtime_dir.name}/{relative_path.as_posix()}"
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

        for source_name, destination_dir in (
            ("cbz", CBZ_DIR),
            ("works", WORKS_DIR),
            ("fanart", FANART_DIR),
        ):
            source_dir = extract_root / source_name
            if destination_dir.exists():
                shutil.rmtree(destination_dir)
            if source_dir.exists():
                shutil.copytree(source_dir, destination_dir)
            else:
                destination_dir.mkdir(parents=True, exist_ok=True)
    return 0
