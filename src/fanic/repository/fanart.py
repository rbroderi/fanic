"""fanart repository domain implementation."""

import sqlite3
import uuid
from pathlib import Path
from typing import NotRequired
from typing import TypedDict

from fanic.db import get_connection
from fanic.settings import FANART_DIR
from fanic.utils import slugify


class FanartItemRow(TypedDict):
    id: str
    uploader_username: str
    uploader_display_name: NotRequired[str]
    title: str
    summary: str
    fandom: str
    rating: str
    image_filename: str
    thumb_filename: str | None
    width: int | None
    height: int | None
    created_at: str
    updated_at: str


class FanartUserSummaryRow(TypedDict):
    uploader_username: str
    item_count: int
    latest_created_at: str
    latest_item_id: str | None
    latest_thumb_filename: str | None


class FanartGalleryRow(TypedDict):
    id: str
    uploader_username: str
    name: str
    slug: str
    description: str
    item_count: int
    created_at: str
    updated_at: str


class FanartCommentRow(TypedDict):
    id: int
    fanart_item_id: str
    username: str
    commenter_display_name: NotRequired[str]
    body: str
    created_at: str


def _to_int(value: object, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped_value = value.strip()
        if not stripped_value:
            return default
        try:
            return int(stripped_value)
        except ValueError:
            return default
    return default


def add_fanart_comment(
    fanart_item_id: str,
    username: str,
    body: str,
) -> None:
    normalized_item_id = fanart_item_id.strip()
    normalized_username = username.strip()
    normalized_body = body.strip()
    if not normalized_item_id:
        raise ValueError("fanart_item_id must not be empty")
    if not normalized_username:
        raise ValueError("username must not be empty")
    if not normalized_body:
        raise ValueError("body must not be empty")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO fanart_comments (fanart_item_id, username, body)
            VALUES (?, ?, ?)
            """,
            (normalized_item_id, normalized_username, normalized_body),
        )


def list_fanart_comments(fanart_item_id: str) -> list[FanartCommentRow]:
    normalized_item_id = fanart_item_id.strip()
    if not normalized_item_id:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.fanart_item_id,
                c.username,
                COALESCE(NULLIF(u.display_name, ''), c.username) AS commenter_display_name,
                c.body,
                c.created_at
            FROM fanart_comments c
            LEFT JOIN users u ON lower(u.username) = lower(c.username)
            WHERE c.fanart_item_id = ?
            ORDER BY c.created_at DESC, c.id DESC
            """,
            (normalized_item_id,),
        ).fetchall()

    comments: list[FanartCommentRow] = []
    for row in rows:
        comments.append(
            {
                "id": int(row["id"]),
                "fanart_item_id": str(row["fanart_item_id"]),
                "username": str(row["username"]),
                "commenter_display_name": str(row["commenter_display_name"]),
                "body": str(row["body"]),
                "created_at": str(row["created_at"]),
            }
        )
    return comments


def _next_available_fanart_gallery_slug(
    connection: sqlite3.Connection,
    uploader_username: str,
    requested_name: str,
) -> str:
    base_slug = slugify(requested_name)
    normalized_base_slug = base_slug if base_slug else "gallery"
    slug_candidate = normalized_base_slug
    suffix = 2

    while True:
        row = connection.execute(
            """
            SELECT 1
            FROM fanart_galleries
            WHERE uploader_username = ? AND slug = ?
            LIMIT 1
            """,
            (uploader_username, slug_candidate),
        ).fetchone()
        if row is None:
            return slug_candidate

        slug_candidate = f"{normalized_base_slug}-{suffix}"
        suffix += 1


def create_fanart_gallery(
    *,
    uploader_username: str,
    name: str,
    description: str = "",
) -> FanartGalleryRow:
    normalized_uploader = uploader_username.strip()
    normalized_name = name.strip()
    normalized_description = description.strip()
    if not normalized_uploader:
        raise ValueError("uploader_username must not be empty")
    if not normalized_name:
        raise ValueError("name must not be empty")

    gallery_id = str(uuid.uuid4())
    with get_connection() as connection:
        slug = _next_available_fanart_gallery_slug(connection, normalized_uploader, normalized_name)
        connection.execute(
            """
            INSERT INTO fanart_galleries (
                id,
                uploader_username,
                name,
                slug,
                description
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                gallery_id,
                normalized_uploader,
                normalized_name,
                slug,
                normalized_description,
            ),
        )

    return {
        "id": gallery_id,
        "uploader_username": normalized_uploader,
        "name": normalized_name,
        "slug": slug,
        "description": normalized_description,
        "item_count": 0,
        "created_at": "",
        "updated_at": "",
    }


def list_fanart_galleries_by_uploader(
    uploader_username: str,
) -> list[FanartGalleryRow]:
    normalized_uploader = uploader_username.strip()
    if not normalized_uploader:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                g.id,
                g.uploader_username,
                g.name,
                g.slug,
                g.description,
                g.created_at,
                g.updated_at,
                COUNT(gi.fanart_item_id) AS item_count
            FROM fanart_galleries g
            LEFT JOIN fanart_gallery_items gi ON gi.gallery_id = g.id
            WHERE g.uploader_username = ?
            GROUP BY g.id, g.uploader_username, g.name, g.slug, g.description, g.created_at, g.updated_at
            ORDER BY g.created_at DESC, g.id DESC
            """,
            (normalized_uploader,),
        ).fetchall()

    galleries: list[FanartGalleryRow] = []
    for row in rows:
        galleries.append(
            {
                "id": str(row["id"]),
                "uploader_username": str(row["uploader_username"]),
                "name": str(row["name"]),
                "slug": str(row["slug"]),
                "description": str(row["description"]),
                "item_count": _to_int(row["item_count"], 0),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return galleries


def get_fanart_gallery_by_slug(
    uploader_username: str,
    gallery_slug: str,
) -> FanartGalleryRow | None:
    normalized_uploader = uploader_username.strip()
    normalized_slug = gallery_slug.strip()
    if not normalized_uploader or not normalized_slug:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                g.id,
                g.uploader_username,
                g.name,
                g.slug,
                g.description,
                g.created_at,
                g.updated_at,
                COUNT(gi.fanart_item_id) AS item_count
            FROM fanart_galleries g
            LEFT JOIN fanart_gallery_items gi ON gi.gallery_id = g.id
            WHERE g.uploader_username = ? AND g.slug = ?
            GROUP BY g.id, g.uploader_username, g.name, g.slug, g.description, g.created_at, g.updated_at
            LIMIT 1
            """,
            (normalized_uploader, normalized_slug),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "name": str(row["name"]),
        "slug": str(row["slug"]),
        "description": str(row["description"]),
        "item_count": _to_int(row["item_count"], 0),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def list_fanart_gallery_item_ids(gallery_id: str) -> set[str]:
    normalized_gallery_id = gallery_id.strip()
    if not normalized_gallery_id:
        return set()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT fanart_item_id
            FROM fanart_gallery_items
            WHERE gallery_id = ?
            ORDER BY position ASC, created_at ASC
            """,
            (normalized_gallery_id,),
        ).fetchall()

    return {str(row["fanart_item_id"]) for row in rows}


def replace_fanart_gallery_items(
    *,
    uploader_username: str,
    gallery_id: str,
    fanart_item_ids: list[str],
) -> int:
    normalized_uploader = uploader_username.strip()
    normalized_gallery_id = gallery_id.strip()
    if not normalized_uploader or not normalized_gallery_id:
        return 0

    seen_item_ids: set[str] = set()
    normalized_item_ids: list[str] = []
    for item_id in fanart_item_ids:
        normalized_item_id = item_id.strip()
        if not normalized_item_id or normalized_item_id in seen_item_ids:
            continue
        seen_item_ids.add(normalized_item_id)
        normalized_item_ids.append(normalized_item_id)

    with get_connection() as connection:
        gallery_row = connection.execute(
            """
            SELECT id
            FROM fanart_galleries
            WHERE id = ? AND uploader_username = ?
            LIMIT 1
            """,
            (normalized_gallery_id, normalized_uploader),
        ).fetchone()
        if gallery_row is None:
            return 0

        valid_ids: list[str] = []
        if normalized_item_ids:
            placeholders = ",".join("?" for _ in normalized_item_ids)
            valid_rows = connection.execute(
                f"""
                SELECT id
                FROM fanart_items
                WHERE uploader_username = ?
                  AND id IN ({placeholders})
                """,
                [normalized_uploader, *normalized_item_ids],
            ).fetchall()
            valid_ids = [str(row["id"]) for row in valid_rows]

        connection.execute(
            "DELETE FROM fanart_gallery_items WHERE gallery_id = ?",
            (normalized_gallery_id,),
        )

        for index, item_id in enumerate(valid_ids):
            connection.execute(
                """
                INSERT INTO fanart_gallery_items (gallery_id, fanart_item_id, position)
                VALUES (?, ?, ?)
                """,
                (normalized_gallery_id, item_id, index),
            )

    return len(valid_ids)


def delete_fanart_gallery(
    *,
    uploader_username: str,
    gallery_id: str,
) -> bool:
    normalized_uploader = uploader_username.strip()
    normalized_gallery_id = gallery_id.strip()
    if not normalized_uploader or not normalized_gallery_id:
        return False

    with get_connection() as connection:
        gallery_row = connection.execute(
            """
            SELECT id
            FROM fanart_galleries
            WHERE id = ? AND uploader_username = ?
            LIMIT 1
            """,
            (normalized_gallery_id, normalized_uploader),
        ).fetchone()
        if gallery_row is None:
            return False

        connection.execute(
            "DELETE FROM fanart_gallery_items WHERE gallery_id = ?",
            (normalized_gallery_id,),
        )
        deleted = connection.execute(
            "DELETE FROM fanart_galleries WHERE id = ? AND uploader_username = ?",
            (normalized_gallery_id, normalized_uploader),
        )

    return deleted.rowcount > 0


def create_fanart_item(
    *,
    item_id: str,
    uploader_username: str,
    title: str,
    summary: str,
    fandom: str = "",
    rating: str = "Not Rated",
    image_filename: str,
    thumb_filename: str | None,
    width: int | None,
    height: int | None,
) -> str:
    normalized_item_id = item_id.strip()
    normalized_uploader = uploader_username.strip()
    if not normalized_item_id:
        raise ValueError("item_id must not be empty")
    if not normalized_uploader:
        raise ValueError("uploader_username must not be empty")
    stripped_rating = rating.strip()
    normalized_rating = stripped_rating if stripped_rating else "Not Rated"

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO fanart_items (
                id,
                uploader_username,
                title,
                summary,
                fandom,
                rating,
                image_filename,
                thumb_filename,
                width,
                height
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_item_id,
                normalized_uploader,
                title,
                summary,
                fandom,
                normalized_rating,
                image_filename,
                thumb_filename,
                width,
                height,
            ),
        )
    return normalized_item_id


def list_fanart_users(
    filters: dict[str, str] | None = None,
    *,
    limit: int = 200,
) -> list[FanartUserSummaryRow]:
    resolved_filters = filters if filters is not None else {}
    where: list[str] = []
    params: list[object] = []

    search = resolved_filters.get("q", "").strip()
    if search:
        where.append("(fi.uploader_username LIKE ? OR fi.title LIKE ? OR fi.summary LIKE ? OR fi.fandom LIKE ?)")
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search, like_search])

    uploader = resolved_filters.get("user", "").strip()
    if uploader:
        where.append("fi.uploader_username LIKE ?")
        like_uploader = f"%{uploader}%"
        params.append(like_uploader)

    fandom = resolved_filters.get("fandom", "").strip()
    if fandom:
        where.append("fi.fandom LIKE ?")
        like_fandom = f"%{fandom}%"
        params.append(like_fandom)

    tag = resolved_filters.get("tag", "").strip()
    if tag:
        where.append("(fi.title LIKE ? OR fi.summary LIKE ?)")
        like_tag = f"%{tag}%"
        params.extend([like_tag, like_tag])

    status = resolved_filters.get("status", "").strip()
    if status == "complete":
        where.append("fi.summary <> ''")
    elif status == "in_progress":
        where.append("fi.summary = ''")

    sort = resolved_filters.get("sort", "newest").strip()
    order_by = "latest_created_at DESC, ranked.uploader_username COLLATE NOCASE ASC"
    if sort == "oldest":
        order_by = "latest_created_at ASC, ranked.uploader_username COLLATE NOCASE ASC"
    elif sort == "title_asc":
        order_by = "ranked.uploader_username COLLATE NOCASE ASC"
    elif sort == "title_desc":
        order_by = "ranked.uploader_username COLLATE NOCASE DESC"

    sql = """
            WITH filtered AS (
                SELECT
                    fi.id,
                    fi.uploader_username,
                    fi.created_at,
                    fi.thumb_filename
                FROM fanart_items fi
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += """
            ),
            ranked AS (
                SELECT
                    filtered.id,
                    filtered.uploader_username,
                    filtered.created_at,
                    filtered.thumb_filename,
                    ROW_NUMBER() OVER (
                        PARTITION BY filtered.uploader_username
                        ORDER BY filtered.created_at DESC, filtered.id DESC
                    ) AS rn
                FROM filtered
            ),
            counts AS (
                SELECT
                    filtered.uploader_username,
                    COUNT(*) AS item_count
                FROM filtered
                GROUP BY filtered.uploader_username
            )
            SELECT
                ranked.uploader_username AS uploader_username,
                counts.item_count AS item_count,
                ranked.created_at AS latest_created_at,
                ranked.id AS latest_item_id,
                ranked.thumb_filename AS latest_thumb_filename
            FROM ranked
            INNER JOIN counts
                ON counts.uploader_username = ranked.uploader_username
            WHERE ranked.rn = 1
    """
    sql += f" ORDER BY {order_by}"
    sql += " LIMIT ?"
    params.append(int(limit))

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    users: list[FanartUserSummaryRow] = []
    for row in rows:
        latest_item_id_obj = row["latest_item_id"]
        thumb_obj = row["latest_thumb_filename"]
        users.append(
            {
                "uploader_username": str(row["uploader_username"]),
                "item_count": _to_int(row["item_count"], 0),
                "latest_created_at": str(row["latest_created_at"]),
                "latest_item_id": (str(latest_item_id_obj) if latest_item_id_obj is not None else None),
                "latest_thumb_filename": (str(thumb_obj) if thumb_obj is not None else None),
            }
        )
    return users


def list_fanart_items(
    filters: dict[str, str] | None = None,
    *,
    limit: int = 200,
) -> list[FanartItemRow]:
    resolved_filters = filters if filters is not None else {}
    where: list[str] = []
    params: list[object] = []

    search = resolved_filters.get("q", "").strip()
    if search:
        where.append(
            "(fi.uploader_username LIKE ? OR fi.title LIKE ? OR fi.summary LIKE ? OR fi.fandom LIKE ? OR u.display_name LIKE ?)"
        )
        like_search = f"%{search}%"
        params.extend([like_search, like_search, like_search, like_search, like_search])

    uploader = resolved_filters.get("user", "").strip()
    if uploader:
        where.append("(fi.uploader_username LIKE ? OR u.display_name LIKE ?)")
        like_uploader = f"%{uploader}%"
        params.extend([like_uploader, like_uploader])

    fandom = resolved_filters.get("fandom", "").strip()
    if fandom:
        where.append("fi.fandom LIKE ?")
        like_fandom = f"%{fandom}%"
        params.append(like_fandom)

    tag = resolved_filters.get("tag", "").strip()
    if tag:
        where.append("(fi.title LIKE ? OR fi.summary LIKE ?)")
        like_tag = f"%{tag}%"
        params.extend([like_tag, like_tag])

    status = resolved_filters.get("status", "").strip()
    if status == "complete":
        where.append("fi.summary <> ''")
    elif status == "in_progress":
        where.append("fi.summary = ''")

    sort = resolved_filters.get("sort", "newest").strip()
    order_by = "fi.created_at DESC, fi.id DESC"
    if sort == "oldest":
        order_by = "fi.created_at ASC, fi.id ASC"
    elif sort == "title_asc":
        order_by = "fi.title COLLATE NOCASE ASC, fi.id ASC"
    elif sort == "title_desc":
        order_by = "fi.title COLLATE NOCASE DESC, fi.id DESC"

    sql = """
            SELECT fi.id, fi.uploader_username,
                   COALESCE(NULLIF(u.display_name, ''), fi.uploader_username) AS uploader_display_name,
                   fi.title, fi.summary, fi.fandom, fi.rating, fi.image_filename, fi.thumb_filename,
                   fi.width, fi.height, fi.created_at, fi.updated_at
            FROM fanart_items fi
            LEFT JOIN users u ON u.username = fi.uploader_username
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_by}"
    sql += " LIMIT ?"
    params.append(int(limit))

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    items: list[FanartItemRow] = []
    for row in rows:
        thumb_obj = row["thumb_filename"]
        width_obj = row["width"]
        height_obj = row["height"]
        items.append(
            {
                "id": str(row["id"]),
                "uploader_username": str(row["uploader_username"]),
                "uploader_display_name": str(row["uploader_display_name"]),
                "title": str(row["title"]),
                "summary": str(row["summary"]),
                "fandom": str(row["fandom"]),
                "rating": str(row["rating"]),
                "image_filename": str(row["image_filename"]),
                "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
                "width": _to_int(width_obj, 0) if width_obj is not None else None,
                "height": _to_int(height_obj, 0) if height_obj is not None else None,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return items


def list_fanart_items_by_uploader(
    uploader_username: str,
    *,
    limit: int = 200,
) -> list[FanartItemRow]:
    normalized_uploader = uploader_username.strip()
    if not normalized_uploader:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
             SELECT fi.id, fi.uploader_username,
                 COALESCE(NULLIF(u.display_name, ''), fi.uploader_username) AS uploader_display_name,
                 fi.title, fi.summary, fi.fandom, fi.rating, fi.image_filename, fi.thumb_filename,
                 fi.width, fi.height, fi.created_at, fi.updated_at
             FROM fanart_items fi
             LEFT JOIN users u ON u.username = fi.uploader_username
             WHERE fi.uploader_username = ?
             ORDER BY fi.created_at DESC, fi.id DESC
            LIMIT ?
            """,
            (normalized_uploader, int(limit)),
        ).fetchall()

    items: list[FanartItemRow] = []
    for row in rows:
        thumb_obj = row["thumb_filename"]
        width_obj = row["width"]
        height_obj = row["height"]
        items.append(
            {
                "id": str(row["id"]),
                "uploader_username": str(row["uploader_username"]),
                "uploader_display_name": str(row["uploader_display_name"]),
                "title": str(row["title"]),
                "summary": str(row["summary"]),
                "fandom": str(row["fandom"]),
                "rating": str(row["rating"]),
                "image_filename": str(row["image_filename"]),
                "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
                "width": _to_int(width_obj, 0) if width_obj is not None else None,
                "height": _to_int(height_obj, 0) if height_obj is not None else None,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return items


def get_fanart_item(item_id: str) -> FanartItemRow | None:
    normalized_item_id = item_id.strip()
    if not normalized_item_id:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, uploader_username, title, summary, fandom, rating, image_filename, thumb_filename,
                   width, height, created_at, updated_at
            FROM fanart_items
            WHERE id = ?
            """,
            (normalized_item_id,),
        ).fetchone()
    if not row:
        return None

    thumb_obj = row["thumb_filename"]
    width_obj = row["width"]
    height_obj = row["height"]
    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "fandom": str(row["fandom"]),
        "rating": str(row["rating"]),
        "image_filename": str(row["image_filename"]),
        "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
        "width": _to_int(width_obj, 0) if width_obj is not None else None,
        "height": _to_int(height_obj, 0) if height_obj is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_fanart_item_by_image(
    uploader_username: str,
    image_filename: str,
) -> FanartItemRow | None:
    normalized_uploader = uploader_username.strip()
    normalized_image = image_filename.strip().lstrip("/")
    if not normalized_uploader or not normalized_image:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
                                                SELECT id, uploader_username, title, summary, fandom, rating, image_filename, thumb_filename,
                   width, height, created_at, updated_at
            FROM fanart_items
            WHERE uploader_username = ?
                                                    AND ltrim(image_filename, '/') = ?
            """,
            (normalized_uploader, normalized_image),
        ).fetchone()
    if not row:
        return None

    thumb_obj = row["thumb_filename"]
    width_obj = row["width"]
    height_obj = row["height"]
    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "fandom": str(row["fandom"]),
        "rating": str(row["rating"]),
        "image_filename": str(row["image_filename"]),
        "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
        "width": _to_int(width_obj, 0) if width_obj is not None else None,
        "height": _to_int(height_obj, 0) if height_obj is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_fanart_item_by_thumb(
    uploader_username: str,
    thumb_filename: str,
) -> FanartItemRow | None:
    normalized_uploader = uploader_username.strip()
    normalized_thumb = thumb_filename.strip().lstrip("/")
    if not normalized_uploader or not normalized_thumb:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
                                                SELECT id, uploader_username, title, summary, fandom, rating, image_filename, thumb_filename,
                   width, height, created_at, updated_at
            FROM fanart_items
            WHERE uploader_username = ?
                                                    AND ltrim(thumb_filename, '/') = ?
            """,
            (normalized_uploader, normalized_thumb),
        ).fetchone()
    if not row:
        return None

    thumb_obj = row["thumb_filename"]
    width_obj = row["width"]
    height_obj = row["height"]
    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "fandom": str(row["fandom"]),
        "rating": str(row["rating"]),
        "image_filename": str(row["image_filename"]),
        "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
        "width": _to_int(width_obj, 0) if width_obj is not None else None,
        "height": _to_int(height_obj, 0) if height_obj is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_fanart_item_by_image_filename(image_filename: str) -> FanartItemRow | None:
    normalized_image = image_filename.strip().lstrip("/")
    if not normalized_image:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                fi.id,
                fi.uploader_username,
                COALESCE(NULLIF(u.display_name, ''), fi.uploader_username) AS uploader_display_name,
                fi.title,
                fi.summary,
                fi.fandom,
                fi.rating,
                fi.image_filename,
                fi.thumb_filename,
                fi.width,
                fi.height,
                fi.created_at,
                fi.updated_at
            FROM fanart_items fi
            LEFT JOIN users u ON lower(u.username) = lower(fi.uploader_username)
            WHERE ltrim(fi.image_filename, '/') = ?
            """,
            (normalized_image,),
        ).fetchone()
    if not row:
        return None

    thumb_obj = row["thumb_filename"]
    width_obj = row["width"]
    height_obj = row["height"]
    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "uploader_display_name": str(row["uploader_display_name"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "fandom": str(row["fandom"]),
        "rating": str(row["rating"]),
        "image_filename": str(row["image_filename"]),
        "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
        "width": _to_int(width_obj, 0) if width_obj is not None else None,
        "height": _to_int(height_obj, 0) if height_obj is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def get_fanart_item_by_thumb_filename(thumb_filename: str) -> FanartItemRow | None:
    normalized_thumb = thumb_filename.strip().lstrip("/")
    if not normalized_thumb:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, uploader_username, title, summary, fandom, rating, image_filename, thumb_filename,
                   width, height, created_at, updated_at
            FROM fanart_items
                 WHERE ltrim(thumb_filename, '/') = ?
            """,
            (normalized_thumb,),
        ).fetchone()
    if not row:
        return None

    thumb_obj = row["thumb_filename"]
    width_obj = row["width"]
    height_obj = row["height"]
    return {
        "id": str(row["id"]),
        "uploader_username": str(row["uploader_username"]),
        "title": str(row["title"]),
        "summary": str(row["summary"]),
        "fandom": str(row["fandom"]),
        "rating": str(row["rating"]),
        "image_filename": str(row["image_filename"]),
        "thumb_filename": str(thumb_obj) if thumb_obj is not None else None,
        "width": _to_int(width_obj, 0) if width_obj is not None else None,
        "height": _to_int(height_obj, 0) if height_obj is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def fanart_file_for(image_name: str) -> Path:
    normalized_image = image_name.strip().lstrip("/")
    return FANART_DIR / "images" / normalized_image


def fanart_thumb_for(thumb_name: str) -> Path:
    normalized_thumb = thumb_name.strip().lstrip("/")
    return FANART_DIR / "thumbs" / normalized_thumb


def delete_fanart_item(item_id: str) -> bool:
    normalized_item_id = item_id.strip()
    if not normalized_item_id:
        return False

    item = get_fanart_item(normalized_item_id)
    if item is None:
        return False

    image_name = str(item.get("image_filename", "")).strip()
    thumb_name_obj = item.get("thumb_filename")
    thumb_name = str(thumb_name_obj).strip() if thumb_name_obj is not None else ""

    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM fanart_items WHERE id = ?",
            (normalized_item_id,),
        )
        if cursor.rowcount < 1:
            return False

        image_in_use = False
        if image_name:
            image_in_use = (
                connection.execute(
                    "SELECT 1 FROM fanart_items WHERE image_filename = ? LIMIT 1",
                    (image_name,),
                ).fetchone()
                is not None
            )

        thumb_in_use = False
        if thumb_name:
            thumb_in_use = (
                connection.execute(
                    "SELECT 1 FROM fanart_items WHERE thumb_filename = ? LIMIT 1",
                    (thumb_name,),
                ).fetchone()
                is not None
            )

    if image_name and not image_in_use:
        try:
            fanart_file_for(image_name).unlink(missing_ok=True)
        except OSError:
            pass

    if thumb_name and not thumb_in_use:
        try:
            fanart_thumb_for(thumb_name).unlink(missing_ok=True)
        except OSError:
            pass

    return True
