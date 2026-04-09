import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from types import TracebackType
from typing import Literal
from typing import override

from fanic.db_migration import run_runtime_migrations
from fanic.media import copy_file
from fanic.media import copy_tree
from fanic.media import delete_file
from fanic.media import delete_tree
from fanic.settings import CBZ_DIR
from fanic.settings import DATA_ROOT
from fanic.settings import DB_PATH
from fanic.settings import FANART_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import ensure_storage_dirs
from fanic.settings import get_settings

_SETTINGS = get_settings()
SCHEMA_PATH = _SETTINGS.package_root / "sql" / "schema.sql"
_DISALLOWED_TEST_ROOTS = (
    Path("/mnt/storage"),
    _SETTINGS.package_root.parent / "runtime",
)


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
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_display_name_unique
        ON users(lower(display_name))
        WHERE trim(display_name) <> ''
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_display_name_nocase
        ON users(display_name COLLATE NOCASE)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
        ON users(lower(email))
        WHERE email IS NOT NULL AND trim(email) <> ''
        """
    )

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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fanart_galleries (
            id TEXT PRIMARY KEY,
            uploader_username TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (uploader_username, slug)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fanart_gallery_items (
            gallery_id TEXT NOT NULL,
            fanart_item_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (gallery_id, fanart_item_id),
            FOREIGN KEY (gallery_id) REFERENCES fanart_galleries(id) ON DELETE CASCADE,
            FOREIGN KEY (fanart_item_id) REFERENCES fanart_items(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_galleries_uploader_created_at
        ON fanart_galleries(uploader_username, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_gallery_items_gallery_position
        ON fanart_gallery_items(gallery_id, position ASC, created_at ASC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_gallery_items_fanart_item
        ON fanart_gallery_items(fanart_item_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_items_title_nocase
        ON fanart_items(title COLLATE NOCASE)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_items_fandom_nocase
        ON fanart_items(fandom COLLATE NOCASE)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fanart_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fanart_item_id TEXT NOT NULL,
            username TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (fanart_item_id) REFERENCES fanart_items(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS fanart_item_tags (
            fanart_item_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (fanart_item_id, tag_id),
            FOREIGN KEY (fanart_item_id) REFERENCES fanart_items(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_comments_item
        ON fanart_comments(fanart_item_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_item_tags_item
        ON fanart_item_tags(fanart_item_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fanart_item_tags_tag
        ON fanart_item_tags(tag_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tag_popularity (
            tag_id INTEGER PRIMARY KEY,
            seed_count INTEGER NOT NULL DEFAULT 0,
            usage_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tag_popularity_usage_seed
        ON tag_popularity(usage_count DESC, seed_count DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_works_title_nocase
        ON works(title COLLATE NOCASE)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS moderation_review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL CHECK (content_type IN ('work', 'fanart')),
            content_id TEXT NOT NULL,
            uploader_username TEXT NOT NULL,
            source_member TEXT NOT NULL DEFAULT '',
            reason_type TEXT NOT NULL CHECK (reason_type IN ('explicit', 'photorealistic', 'graphic-violence')),
            confidence REAL NOT NULL,
            min_threshold REAL NOT NULL,
            max_threshold REAL NOT NULL,
            moderation_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'dismissed')),
            reviewed_by TEXT,
            reviewed_at TEXT,
            review_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_moderation_review_queue_status_created_at
        ON moderation_review_queue(status, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_moderation_review_queue_pending_unique
        ON moderation_review_queue(content_type, content_id, source_member, reason_type, status)
        """
    )

    # Build a fanart FTS index for scalable prefix search across uploader/title/summary/fandom.
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS fanart_search
        USING fts5(
            fanart_item_id UNINDEXED,
            uploader_username,
            uploader_display_name,
            title,
            summary,
            fandom,
            tokenize = 'unicode61',
            prefix = '2 3 4'
        )
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS fanart_search_ai
        AFTER INSERT ON fanart_items
        BEGIN
            INSERT INTO fanart_search(
                rowid,
                fanart_item_id,
                uploader_username,
                uploader_display_name,
                title,
                summary,
                fandom
            )
            VALUES (
                NEW.rowid,
                NEW.id,
                NEW.uploader_username,
                COALESCE(
                    NULLIF(
                        (
                            SELECT u.display_name
                            FROM users u
                            WHERE u.username = NEW.uploader_username
                            LIMIT 1
                        ),
                        ''
                    ),
                    NEW.uploader_username
                ),
                NEW.title,
                NEW.summary,
                NEW.fandom
            );
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS fanart_search_ad
        AFTER DELETE ON fanart_items
        BEGIN
            DELETE FROM fanart_search WHERE rowid = OLD.rowid;
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS fanart_search_au
        AFTER UPDATE OF id, uploader_username, title, summary, fandom ON fanart_items
        BEGIN
            DELETE FROM fanart_search WHERE rowid = OLD.rowid;
            INSERT INTO fanart_search(
                rowid,
                fanart_item_id,
                uploader_username,
                uploader_display_name,
                title,
                summary,
                fandom
            )
            VALUES (
                NEW.rowid,
                NEW.id,
                NEW.uploader_username,
                COALESCE(
                    NULLIF(
                        (
                            SELECT u.display_name
                            FROM users u
                            WHERE u.username = NEW.uploader_username
                            LIMIT 1
                        ),
                        ''
                    ),
                    NEW.uploader_username
                ),
                NEW.title,
                NEW.summary,
                NEW.fandom
            );
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS fanart_search_users_au
        AFTER UPDATE OF display_name ON users
        BEGIN
            DELETE FROM fanart_search
            WHERE rowid IN (
                SELECT fi.rowid
                FROM fanart_items fi
                WHERE fi.uploader_username = NEW.username
            );
            INSERT INTO fanart_search(
                rowid,
                fanart_item_id,
                uploader_username,
                uploader_display_name,
                title,
                summary,
                fandom
            )
            SELECT
                fi.rowid,
                fi.id,
                fi.uploader_username,
                COALESCE(NULLIF(NEW.display_name, ''), fi.uploader_username),
                fi.title,
                fi.summary,
                fi.fandom
            FROM fanart_items fi
            WHERE fi.uploader_username = NEW.username;
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS fanart_search_users_ai
        AFTER INSERT ON users
        BEGIN
            DELETE FROM fanart_search
            WHERE rowid IN (
                SELECT fi.rowid
                FROM fanart_items fi
                WHERE fi.uploader_username = NEW.username
            );
            INSERT INTO fanart_search(
                rowid,
                fanart_item_id,
                uploader_username,
                uploader_display_name,
                title,
                summary,
                fandom
            )
            SELECT
                fi.rowid,
                fi.id,
                fi.uploader_username,
                COALESCE(NULLIF(NEW.display_name, ''), fi.uploader_username),
                fi.title,
                fi.summary,
                fi.fandom
            FROM fanart_items fi
            WHERE fi.uploader_username = NEW.username;
        END
        """
    )

    fanart_item_count_row = connection.execute("SELECT COUNT(*) AS count FROM fanart_items").fetchone()
    fanart_search_count_row = connection.execute("SELECT COUNT(*) AS count FROM fanart_search").fetchone()
    fanart_item_count = int(fanart_item_count_row[0]) if fanart_item_count_row else 0
    fanart_search_count = int(fanart_search_count_row[0]) if fanart_search_count_row else 0
    if fanart_search_count != fanart_item_count:
        connection.execute("DELETE FROM fanart_search")
        connection.execute(
            """
            INSERT INTO fanart_search(
                rowid,
                fanart_item_id,
                uploader_username,
                uploader_display_name,
                title,
                summary,
                fandom
            )
            SELECT
                fi.rowid,
                fi.id,
                fi.uploader_username,
                COALESCE(NULLIF(u.display_name, ''), fi.uploader_username),
                fi.title,
                fi.summary,
                fi.fandom
            FROM fanart_items fi
            LEFT JOIN users u ON u.username = fi.uploader_username
            """
        )

    # Build a works FTS index for scalable prefix search across title/summary/fandom/display name.
    connection.execute(
        """
                CREATE VIRTUAL TABLE IF NOT EXISTS works_search
                USING fts5(
                    work_id UNINDEXED,
                    title,
                    summary,
                    fandom,
                    uploader_username,
                    uploader_display_name,
                    tokenize = 'unicode61',
                    prefix = '2 3 4'
                )
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_ai
                AFTER INSERT ON works
                BEGIN
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    VALUES (
                        NEW.rowid,
                        NEW.id,
                        NEW.title,
                        NEW.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = NEW.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(NEW.uploader_username, ''),
                        COALESCE(
                            NULLIF(
                                (
                                    SELECT u.display_name
                                    FROM users u
                                    WHERE u.username = NEW.uploader_username
                                    LIMIT 1
                                ),
                                ''
                            ),
                            COALESCE(NEW.uploader_username, '')
                        )
                    );
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_ad
                AFTER DELETE ON works
                BEGIN
                    DELETE FROM works_search WHERE rowid = OLD.rowid;
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_au
                AFTER UPDATE OF id, title, summary, uploader_username ON works
                BEGIN
                    DELETE FROM works_search WHERE rowid = OLD.rowid;
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    VALUES (
                        NEW.rowid,
                        NEW.id,
                        NEW.title,
                        NEW.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = NEW.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(NEW.uploader_username, ''),
                        COALESCE(
                            NULLIF(
                                (
                                    SELECT u.display_name
                                    FROM users u
                                    WHERE u.username = NEW.uploader_username
                                    LIMIT 1
                                ),
                                ''
                            ),
                            COALESCE(NEW.uploader_username, '')
                        )
                    );
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_work_tags_ai
                AFTER INSERT ON work_tags
                BEGIN
                    DELETE FROM works_search
                    WHERE rowid IN (
                        SELECT w.rowid
                        FROM works w
                        WHERE w.id = NEW.work_id
                    );
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    SELECT
                        w.rowid,
                        w.id,
                        w.title,
                        w.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = w.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(w.uploader_username, ''),
                        COALESCE(NULLIF(u.display_name, ''), COALESCE(w.uploader_username, ''))
                    FROM works w
                    LEFT JOIN users u ON u.username = w.uploader_username
                    WHERE w.id = NEW.work_id;
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_work_tags_ad
                AFTER DELETE ON work_tags
                BEGIN
                    DELETE FROM works_search
                    WHERE rowid IN (
                        SELECT w.rowid
                        FROM works w
                        WHERE w.id = OLD.work_id
                    );
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    SELECT
                        w.rowid,
                        w.id,
                        w.title,
                        w.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = w.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(w.uploader_username, ''),
                        COALESCE(NULLIF(u.display_name, ''), COALESCE(w.uploader_username, ''))
                    FROM works w
                    LEFT JOIN users u ON u.username = w.uploader_username
                    WHERE w.id = OLD.work_id;
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_tags_au
                AFTER UPDATE OF name, type ON tags
                BEGIN
                    DELETE FROM works_search
                    WHERE rowid IN (
                        SELECT w.rowid
                        FROM works w
                        JOIN work_tags wt ON wt.work_id = w.id
                        WHERE wt.tag_id = NEW.id
                    );
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    SELECT
                        w.rowid,
                        w.id,
                        w.title,
                        w.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt2
                                JOIN tags t ON t.id = wt2.tag_id
                                WHERE wt2.work_id = w.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(w.uploader_username, ''),
                        COALESCE(NULLIF(u.display_name, ''), COALESCE(w.uploader_username, ''))
                    FROM works w
                    LEFT JOIN users u ON u.username = w.uploader_username
                    JOIN work_tags wt ON wt.work_id = w.id
                    WHERE wt.tag_id = NEW.id;
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_users_ai
                AFTER INSERT ON users
                BEGIN
                    DELETE FROM works_search
                    WHERE rowid IN (
                        SELECT w.rowid
                        FROM works w
                        WHERE w.uploader_username = NEW.username
                    );
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    SELECT
                        w.rowid,
                        w.id,
                        w.title,
                        w.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = w.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(w.uploader_username, ''),
                        COALESCE(NULLIF(NEW.display_name, ''), COALESCE(w.uploader_username, ''))
                    FROM works w
                    WHERE w.uploader_username = NEW.username;
                END
                """
    )
    connection.execute(
        """
                CREATE TRIGGER IF NOT EXISTS works_search_users_au
                AFTER UPDATE OF display_name ON users
                BEGIN
                    DELETE FROM works_search
                    WHERE rowid IN (
                        SELECT w.rowid
                        FROM works w
                        WHERE w.uploader_username = NEW.username
                    );
                    INSERT INTO works_search(
                        rowid,
                        work_id,
                        title,
                        summary,
                        fandom,
                        uploader_username,
                        uploader_display_name
                    )
                    SELECT
                        w.rowid,
                        w.id,
                        w.title,
                        w.summary,
                        COALESCE(
                            (
                                SELECT group_concat(t.name, ' ')
                                FROM work_tags wt
                                JOIN tags t ON t.id = wt.tag_id
                                WHERE wt.work_id = w.id
                                  AND t.type = 'fandom'
                            ),
                            ''
                        ),
                        COALESCE(w.uploader_username, ''),
                        COALESCE(NULLIF(NEW.display_name, ''), COALESCE(w.uploader_username, ''))
                    FROM works w
                    WHERE w.uploader_username = NEW.username;
                END
                """
    )

    work_count_row = connection.execute("SELECT COUNT(*) FROM works").fetchone()
    work_search_count_row = connection.execute("SELECT COUNT(*) FROM works_search").fetchone()
    work_count = int(work_count_row[0]) if work_count_row else 0
    work_search_count = int(work_search_count_row[0]) if work_search_count_row else 0
    if work_count != work_search_count:
        connection.execute("DELETE FROM works_search")
        connection.execute(
            """
            INSERT INTO works_search(
                rowid,
                work_id,
                title,
                summary,
                fandom,
                uploader_username,
                uploader_display_name
            )
            SELECT
                w.rowid,
                w.id,
                w.title,
                w.summary,
                COALESCE(
                    (
                        SELECT group_concat(t.name, ' ')
                        FROM work_tags wt
                        JOIN tags t ON t.id = wt.tag_id
                        WHERE wt.work_id = w.id
                          AND t.type = 'fandom'
                    ),
                    ''
                ),
                COALESCE(w.uploader_username, ''),
                COALESCE(NULLIF(u.display_name, ''), COALESCE(w.uploader_username, ''))
            FROM works w
            LEFT JOIN users u ON u.username = w.uploader_username
            """
        )

    run_runtime_migrations(connection, _table_exists)


def get_connection() -> sqlite3.Connection:
    if os.environ.get("PYTEST_VERSION"):
        test_db_path_raw = os.environ.get("FANIC_DB_PATH")
        if not test_db_path_raw:
            raise RuntimeError("Tests must set FANIC_DB_PATH to an isolated test database path before loading fanic.db")

        test_db_path = Path(test_db_path_raw).expanduser().resolve()
        if test_db_path.name != "fanic.test.db" and ".pytest-runtime" not in test_db_path.as_posix():
            raise RuntimeError(
                "Unsafe test DB path. Use a dedicated test DB path (recommended: .pytest-runtime/fanic.test.db)."
            )

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
                delete_tree(child)
            else:
                delete_file(child)

    if DB_PATH.exists() and DB_PATH.parent != DATA_ROOT:
        delete_file(DB_PATH)


def _assert_pytest_safe_destructive_target(operation: str) -> None:
    if not os.environ.get("PYTEST_VERSION"):
        return

    data_root = DATA_ROOT.resolve()
    db_path = DB_PATH.resolve()
    for disallowed_root in _DISALLOWED_TEST_ROOTS:
        root = disallowed_root.resolve()
        if data_root.is_relative_to(root) or db_path.is_relative_to(root):
            raise RuntimeError(
                f"Refusing {operation} under pytest for production-like paths: DATA_ROOT={data_root}, DB_PATH={db_path}"
            )


def initialize_database(schema_path: Path = SCHEMA_PATH, *, reset: bool = False) -> int:
    if reset:
        _assert_pytest_safe_destructive_target("initialize_database(reset=True)")
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


def run_database_migrations() -> int:
    ensure_storage_dirs()
    with sqlite3.connect(DB_PATH, factory=_ManagedConnection) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA synchronous = NORMAL;")
        connection.execute("PRAGMA busy_timeout = 5000;")
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
            raise FileExistsError("Data directory is not empty. Re-run with force=True to overwrite it.")
        _assert_pytest_safe_destructive_target("restore_runtime_backup(force=True)")
        delete_tree(DATA_ROOT)

    with tempfile.TemporaryDirectory(prefix="fanic-restore-") as tmp_dir:
        extract_root = Path(tmp_dir) / "extract"
        with zipfile.ZipFile(resolved_backup_path, mode="r") as archive:
            member_names = {info.filename.strip("/") for info in archive.infolist()}
            _safe_extract_zip(archive, extract_root)

        has_runtime_payload = any(
            name == "fanic.db" or name.startswith("cbz/") or name.startswith("works/") for name in member_names
        )
        if not has_runtime_payload:
            raise ValueError("Backup archive does not contain FANIC runtime data")

        ensure_storage_dirs()
        restored_db = extract_root / DB_PATH.name
        if restored_db.exists():
            _ = copy_file(restored_db, DB_PATH)

        for source_name, destination_dir in (
            ("cbz", CBZ_DIR),
            ("works", WORKS_DIR),
            ("fanart", FANART_DIR),
        ):
            source_dir = extract_root / source_name
            if destination_dir.exists():
                delete_tree(destination_dir)
            if source_dir.exists():
                _ = copy_tree(source_dir, destination_dir)
            else:
                destination_dir.mkdir(parents=True, exist_ok=True)
    return 0
