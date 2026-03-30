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
