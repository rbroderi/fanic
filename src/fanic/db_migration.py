import sqlite3
import warnings
from collections.abc import Callable


def run_runtime_migrations(
    connection: sqlite3.Connection,
    table_exists: Callable[[sqlite3.Connection, str], bool],
) -> None:
    warnings.warn(
        "legacy runtime migrations are deprecated and should be removed once db migrated.",
        DeprecationWarning,
        stacklevel=2,
    )
    if table_exists(connection, "fanart_items"):
        # Normalize legacy stored paths like "/_objects/..." so path joins
        # stay rooted under FANART_DIR.
        connection.execute(
            """
            UPDATE fanart_items
            SET image_filename = ltrim(image_filename, '/')
            WHERE image_filename LIKE '/%'
            """
        )
        connection.execute(
            """
            UPDATE fanart_items
            SET thumb_filename = ltrim(thumb_filename, '/')
            WHERE thumb_filename LIKE '/%'
            """
        )

    if table_exists(connection, "moderation_review_queue"):
        row = connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'moderation_review_queue'
            """
        ).fetchone()
        create_sql = str(row[0]).lower() if row is not None and row[0] is not None else ""
        if "graphic-violence" not in create_sql:
            connection.execute("DROP INDEX IF EXISTS idx_moderation_review_queue_status_created_at")
            connection.execute("DROP INDEX IF EXISTS idx_moderation_review_queue_pending_unique")
            connection.execute("ALTER TABLE moderation_review_queue RENAME TO moderation_review_queue_legacy")
            connection.execute(
                """
                CREATE TABLE moderation_review_queue (
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
                INSERT INTO moderation_review_queue (
                    id,
                    content_type,
                    content_id,
                    uploader_username,
                    source_member,
                    reason_type,
                    confidence,
                    min_threshold,
                    max_threshold,
                    moderation_json,
                    status,
                    reviewed_by,
                    reviewed_at,
                    review_note,
                    created_at
                )
                SELECT
                    id,
                    content_type,
                    content_id,
                    uploader_username,
                    source_member,
                    reason_type,
                    confidence,
                    min_threshold,
                    max_threshold,
                    moderation_json,
                    status,
                    reviewed_by,
                    reviewed_at,
                    review_note,
                    created_at
                FROM moderation_review_queue_legacy
                """
            )
            connection.execute("DROP TABLE moderation_review_queue_legacy")
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
