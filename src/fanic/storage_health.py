from dataclasses import dataclass

from fanic.db import get_connection
from fanic.settings import FANART_DIR


@dataclass(frozen=True)
class FanartStorageHealth:
    status: str
    db_items: int
    checked_items: int
    missing_image_files: int
    missing_thumb_files: int
    image_dir_exists: bool
    thumb_dir_exists: bool


def get_fanart_storage_health(*, max_rows_to_check: int = 200) -> FanartStorageHealth:
    normalized_limit = int(max_rows_to_check) if int(max_rows_to_check) > 0 else 1
    image_dir = FANART_DIR / "images"
    thumb_dir = FANART_DIR / "thumbs"
    image_dir_exists = image_dir.is_dir()
    thumb_dir_exists = thumb_dir.is_dir()

    with get_connection() as connection:
        count_row = connection.execute("SELECT COUNT(*) AS total FROM fanart_items").fetchone()
        db_items = int(count_row["total"]) if count_row is not None else 0
        rows = connection.execute(
            """
            SELECT image_filename, thumb_filename
            FROM fanart_items
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()

    missing_image_files = 0
    missing_thumb_files = 0
    for row in rows:
        image_name = str(row["image_filename"]).strip()
        if image_name:
            image_file = image_dir / image_name.lstrip("/")
            if not image_file.is_file():
                missing_image_files += 1

        thumb_name_obj = row["thumb_filename"]
        thumb_name = str(thumb_name_obj).strip() if thumb_name_obj is not None else ""
        if thumb_name:
            thumb_file = thumb_dir / thumb_name.lstrip("/")
            if not thumb_file.is_file():
                missing_thumb_files += 1

    if not image_dir_exists or not thumb_dir_exists:
        status = "down" if db_items > 0 else "degraded"
    elif missing_image_files > 0 or missing_thumb_files > 0:
        status = "degraded"
    else:
        status = "up"

    return FanartStorageHealth(
        status=status,
        db_items=db_items,
        checked_items=len(rows),
        missing_image_files=missing_image_files,
        missing_thumb_files=missing_thumb_files,
        image_dir_exists=image_dir_exists,
        thumb_dir_exists=thumb_dir_exists,
    )
