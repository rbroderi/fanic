"""works repository domain implementation."""

import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import NotRequired
from typing import TypedDict
from typing import cast
from urllib.parse import quote
from urllib.parse import urlsplit

import tomli_w

from fanic.db import get_connection
from fanic.media import delete_file
from fanic.media import delete_tree
from fanic.media import get_media_service
from fanic.media import media_public_path_from_key
from fanic.settings import CBZ_DIR
from fanic.settings import WORKS_DIR
from fanic.type_coercion import as_int
from fanic.utils import slugify

TAG_FIELD_TO_TYPE = {
    "fandoms": "fandom",
    "relationships": "relationship",
    "characters": "character",
    "freeform_tags": "freeform",
}

_FTS_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _csv_terms(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


class WorkComment(TypedDict):
    id: int
    username: str
    commenter_display_name: NotRequired[str]
    chapter_number: int | None
    body: str
    created_at: str


class WorkListItem(TypedDict):
    id: str
    slug: str
    title: str
    summary: str
    status: str
    rating: str
    warnings: str
    page_count: int
    cover_page_index: int
    cover_image_filename: NotRequired[str]
    cover_thumb_filename: NotRequired[str]
    updated_at: str
    uploader_username: NotRequired[str]


class WorkVersionSummary(TypedDict):
    version_id: str
    created_at: str
    action: str
    actor: str
    page_count: int


class WorkPageRow(TypedDict):
    page_index: int
    image_filename: str
    thumb_filename: str | None
    width: int | None
    height: int | None


class WorkChapterRow(TypedDict):
    id: int
    chapter_index: int
    title: str
    start_page: int
    end_page: int
    created_at: str


def _versions_dir_for_work(work_id: str) -> Path:
    return WORKS_DIR / work_id / "versions"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_version_id() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S_%fZ")


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in cast(list[object], value):
        text = str(item)
        if text.strip():
            result.append(text)
    return result


def _as_string_object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _strip_none_values(value: object) -> object:
    value_dict = _as_string_object_dict(value)
    if value_dict is not None:
        return {
            str(key_obj): _strip_none_values(item_obj)
            for key_obj, item_obj in value_dict.items()
            if item_obj is not None
        }
    if isinstance(value, list):
        return [_strip_none_values(item) for item in cast(list[object], value)]
    return value


def _work_id_for_chapter(chapter_id: int) -> str | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT work_id FROM work_chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
    if not row:
        return None
    return str(row["work_id"])


def list_work_comments(work_id: str) -> list[WorkComment]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.username,
                COALESCE(NULLIF(u.display_name, ''), c.username) AS commenter_display_name,
                c.chapter_number,
                c.body,
                c.created_at
            FROM work_comments c
            LEFT JOIN users u ON lower(u.username) = lower(c.username)
            WHERE work_id = ?
            ORDER BY c.created_at DESC, c.id DESC
            """,
            (work_id,),
        ).fetchall()
    comments: list[WorkComment] = []
    for row in rows:
        chapter_number_raw = row["chapter_number"]
        chapter_number = int(chapter_number_raw) if chapter_number_raw is not None else None
        comments.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "commenter_display_name": str(row["commenter_display_name"]),
                "chapter_number": chapter_number,
                "body": str(row["body"]),
                "created_at": str(row["created_at"]),
            }
        )
    return comments


def work_kudos_count(work_id: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM work_kudos WHERE work_id = ?",
            (work_id,),
        ).fetchone()
    if not row:
        return 0
    return int(row["count"])


def get_work(work_id: str) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        if not row:
            return None

        work = dict(row)
        work["creators"] = json.loads(work.get("creators", "[]"))

        tags = connection.execute(
            """
            SELECT t.name, t.slug, t.type
            FROM work_tags wt
            JOIN tags t ON t.id = wt.tag_id
            WHERE wt.work_id = ?
            ORDER BY t.type, t.name
            """,
            (work_id,),
        ).fetchall()
        work["tags"] = [dict(tag) for tag in tags]
        return work


def list_work_chapters(work_id: str) -> list[WorkChapterRow]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, chapter_index, title, start_page, end_page, created_at
            FROM work_chapters
            WHERE work_id = ?
            ORDER BY chapter_index
            """,
            (work_id,),
        ).fetchall()
    chapter_rows: list[WorkChapterRow] = []
    for row in rows:
        chapter_rows.append(
            {
                "id": as_int(row["id"], 0),
                "chapter_index": as_int(row["chapter_index"], 0),
                "title": str(row["title"]),
                "start_page": as_int(row["start_page"], 1),
                "end_page": as_int(row["end_page"], 1),
                "created_at": str(row["created_at"]),
            }
        )
    return chapter_rows


def sync_work_metadata_toml(work_id: str) -> None:
    work = get_work(work_id)
    if not work:
        return

    tags: list[dict[str, object]] = []
    raw_tags = work.get("tags", [])
    if isinstance(raw_tags, list):
        for tag in cast(list[object], raw_tags):
            tag_map = _as_string_object_dict(tag)
            if tag_map is not None:
                tags.append(
                    {
                        "name": str(tag_map.get("name", "")),
                        "slug": str(tag_map.get("slug", "")),
                        "type": str(tag_map.get("type", "")),
                    }
                )

    raw_chapters = list_work_chapters(work_id)
    chapters: list[dict[str, object]] = []
    for chapter in raw_chapters:
        chapters.append(
            {
                "id": chapter["id"],
                "chapter_index": chapter["chapter_index"],
                "title": chapter["title"],
                "start_page": chapter["start_page"],
                "end_page": chapter["end_page"],
                "created_at": chapter["created_at"],
            }
        )

    creators = _list_of_strings(work.get("creators", []))

    payload = {
        "work": {
            "id": str(work.get("id", work_id)),
            "slug": str(work.get("slug", "")),
            "title": str(work.get("title", "Untitled")),
            "summary": str(work.get("summary", "")),
            "rating": str(work.get("rating", "Not Rated")),
            "warnings": str(work.get("warnings", "")),
            "language": str(work.get("language", "en")),
            "status": str(work.get("status", "in_progress")),
            "creators": [str(name) for name in creators],
            "series_name": work.get("series_name"),
            "series_index": work.get("series_index"),
            "published_at": work.get("published_at"),
            "cover_page_index": as_int(work.get("cover_page_index", 1), 1),
            "page_count": as_int(work.get("page_count", 0), 0),
            "cbz_path": str(work.get("cbz_path", "")),
            "uploader_username": work.get("uploader_username"),
            "created_at": work.get("created_at"),
            "updated_at": work.get("updated_at"),
            "last_metadata_editor": work.get("last_metadata_editor"),
            "last_metadata_edited_at": work.get("last_metadata_edited_at"),
            "last_metadata_edited_by_admin": bool(as_int(work.get("last_metadata_edited_by_admin", 0), 0)),
        },
        "tags": tags,
        "chapters": chapters,
        "kudos": {"count": work_kudos_count(work_id)},
        "comments": list_work_comments(work_id),
    }

    clean_payload_obj = _strip_none_values(payload)
    clean_payload = _as_string_object_dict(clean_payload_obj)
    if clean_payload is None:
        return
    work_dir = WORKS_DIR / work_id
    work_dir.mkdir(parents=True, exist_ok=True)
    metadata_toml_path = work_dir / "metadata.toml"
    metadata_toml_path.write_text(
        tomli_w.dumps(clean_payload),
        encoding="utf-8",
    )

    # Legacy snapshot files are deprecated in favor of metadata.toml.
    for legacy_name in ("manifest.json", "metadata.json"):
        try:
            delete_file(work_dir / legacy_name, missing_ok=True)
        except OSError:
            pass


def work_is_explicit(work: Mapping[str, object]) -> bool:
    return str(work.get("rating", "")).strip().lower() == "explicit"


def work_is_mature(work: Mapping[str, object]) -> bool:
    return str(work.get("rating", "")).strip().lower() == "mature"


def user_prefers_mature(username: str | None) -> bool:
    if not username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            "SELECT view_mature_rated FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        return bool(int(row["view_mature_rated"]))


def user_prefers_explicit(username: str | None) -> bool:
    if not username:
        return False

    with get_connection() as connection:
        row = connection.execute(
            "SELECT view_explicit_rated FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return False
        return bool(int(row["view_explicit_rated"]))


def can_view_work(username: str | None, work: Mapping[str, object]) -> bool:
    if work_is_explicit(work):
        return user_prefers_explicit(username)
    if work_is_mature(work):
        return user_prefers_mature(username)
    return True


def add_work_comment(
    work_id: str,
    username: str,
    body: str,
    chapter_number: int | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO work_comments (work_id, username, chapter_number, body)
            VALUES (?, ?, ?, ?)
            """,
            (work_id, username, chapter_number, body),
        )
    sync_work_metadata_toml(work_id)


def add_work_kudo(work_id: str, username: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO work_kudos (work_id, username)
            VALUES (?, ?)
            """,
            (work_id, username),
        )
    sync_work_metadata_toml(work_id)
    return cursor.rowcount > 0


def count_uploaded_pages_for_user(username: str | None) -> int:
    if not username:
        return 0

    normalized_username = username.strip()
    if not normalized_username:
        return 0

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(page_count), 0) AS page_count_total
            FROM works
            WHERE uploader_username = ?
            """,
            (normalized_username,),
        ).fetchone()
    if not row:
        return 0
    return int(row["page_count_total"])


def has_user_kudoed_work(work_id: str, username: str | None) -> bool:
    if not username:
        return False
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM work_kudos WHERE work_id = ? AND username = ?",
            (work_id, username),
        ).fetchone()
    return bool(row)


def upsert_work(work: dict[str, object]) -> None:
    warnings_value = work.get("warnings", "No Archive Warnings Apply")
    if isinstance(warnings_value, list):
        warnings_text = ", ".join(_list_of_strings(cast(object, warnings_value)))
    else:
        warnings_text = str(warnings_value)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO works (
                id, slug, title, summary, rating, warnings, language, status,
                creators, series_name, series_index, published_at,
                cover_page_index, page_count, cbz_path, uploader_username
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slug=excluded.slug,
                title=excluded.title,
                summary=excluded.summary,
                rating=excluded.rating,
                warnings=excluded.warnings,
                language=excluded.language,
                status=excluded.status,
                creators=excluded.creators,
                series_name=excluded.series_name,
                series_index=excluded.series_index,
                published_at=excluded.published_at,
                cover_page_index=excluded.cover_page_index,
                page_count=excluded.page_count,
                cbz_path=excluded.cbz_path,
                uploader_username=COALESCE(works.uploader_username, excluded.uploader_username),
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                work["id"],
                work["slug"],
                work["title"],
                work.get("summary", ""),
                work.get("rating", "Not Rated"),
                warnings_text,
                work.get("language", "en"),
                work.get("status", "in_progress"),
                json.dumps(work.get("creators", []), ensure_ascii=True),
                work.get("series"),
                work.get("series_index"),
                work.get("published_at"),
                as_int(work.get("cover_page_index", 1), 1),
                as_int(work.get("page_count", 0), 0),
                work["cbz_path"],
                work.get("uploader_username"),
            ),
        )
    sync_work_metadata_toml(str(work["id"]))


def set_work_cbz_path(work_id: str, cbz_path: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE works SET cbz_path = ? WHERE id = ?",
            (cbz_path, work_id),
        )
    sync_work_metadata_toml(work_id)


def _ensure_tag(
    name: str,
    tag_type: str,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    slug = slugify(name)
    if connection is None:
        with get_connection() as managed_connection:
            return _ensure_tag(name, tag_type, connection=managed_connection)

    existing = connection.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
    if existing:
        return int(existing["id"])

    cursor = connection.execute(
        "INSERT INTO tags (slug, name, type) VALUES (?, ?, ?)",
        (slug, name, tag_type),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to insert tag")
    return int(cursor.lastrowid)


def _increment_tag_usage_counts(connection: sqlite3.Connection, tag_ids: set[int]) -> None:
    for tag_id in tag_ids:
        connection.execute(
            """
            INSERT INTO tag_popularity (tag_id, usage_count)
            VALUES (?, 1)
            ON CONFLICT(tag_id) DO UPDATE SET
                usage_count = tag_popularity.usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (tag_id,),
        )


def replace_work_tags(work_id: str, metadata: dict[str, object]) -> None:
    tag_pairs: list[tuple[str, str]] = []

    for field_name, tag_type in TAG_FIELD_TO_TYPE.items():
        names_value = metadata.get(field_name, [])
        if isinstance(names_value, list):
            for name in cast(list[object], names_value):
                if isinstance(name, str) and name:
                    tag_pairs.append((name, tag_type))

    rating = metadata.get("rating")
    if isinstance(rating, str) and rating:
        tag_pairs.append((rating, "rating"))

    warnings = metadata.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [warnings]
    if isinstance(warnings, list):
        for warning in cast(list[object], warnings):
            if isinstance(warning, str) and warning:
                tag_pairs.append((warning, "archive_warning"))

    unique_tag_pairs = list(dict.fromkeys(tag_pairs))

    with get_connection() as connection:
        existing_rows = connection.execute(
            "SELECT tag_id FROM work_tags WHERE work_id = ?",
            (work_id,),
        ).fetchall()
        existing_tag_ids = {int(row["tag_id"]) for row in existing_rows}

        connection.execute(
            "DELETE FROM work_tags WHERE work_id = ?",
            (work_id,),
        )

        new_tag_ids: set[int] = set()
        for name, tag_type in unique_tag_pairs:
            tag_id = _ensure_tag(name, tag_type, connection=connection)
            new_tag_ids.add(tag_id)
            connection.execute(
                "INSERT OR IGNORE INTO work_tags (work_id, tag_id) VALUES (?, ?)",
                (work_id, tag_id),
            )

        added_tag_ids = new_tag_ids - existing_tag_ids
        _increment_tag_usage_counts(connection, added_tag_ids)
    sync_work_metadata_toml(work_id)


def update_work_metadata(
    work_id: str,
    metadata: dict[str, object],
    editor_username: str,
    edited_by_admin: bool,
) -> None:
    warnings_value = metadata.get("warnings", "")
    if isinstance(warnings_value, list):
        warnings_text = ", ".join(_list_of_strings(cast(object, warnings_value)))
    else:
        warnings_text = str(warnings_value)

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE works
            SET
                title = ?,
                summary = ?,
                rating = ?,
                warnings = ?,
                language = ?,
                status = ?,
                series_name = ?,
                series_index = ?,
                published_at = ?,
                last_metadata_editor = ?,
                last_metadata_edited_at = CURRENT_TIMESTAMP,
                last_metadata_edited_by_admin = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                metadata.get("title", ""),
                metadata.get("summary", ""),
                metadata.get("rating", "Not Rated"),
                warnings_text,
                metadata.get("language", "en"),
                metadata.get("status", "in_progress"),
                metadata.get("series", "") if metadata.get("series", "") else None,
                metadata.get("series_index"),
                metadata.get("published_at", "") if metadata.get("published_at", "") else None,
                editor_username,
                1 if edited_by_admin else 0,
                work_id,
            ),
        )

    replace_work_tags(work_id, metadata)
    sync_work_metadata_toml(work_id)


def set_work_rating(
    work_id: str,
    rating: str,
    *,
    editor_username: str,
    edited_by_admin: bool,
) -> bool:
    existing_work = get_work(work_id)
    if not existing_work:
        return False

    metadata: dict[str, object] = {
        "title": str(existing_work.get("title", "Untitled")),
        "summary": str(existing_work.get("summary", "")),
        "rating": rating,
        "warnings": str(existing_work.get("warnings", "No Archive Warnings Apply")),
        "language": str(existing_work.get("language", "en")),
        "status": str(existing_work.get("status", "in_progress")),
        "series": (existing_work.get("series_name") if existing_work.get("series_name") else ""),
        "series_index": existing_work.get("series_index"),
        "published_at": (existing_work.get("published_at") if existing_work.get("published_at") else ""),
    }
    update_work_metadata(
        work_id,
        metadata,
        editor_username=editor_username,
        edited_by_admin=edited_by_admin,
    )
    return True


def replace_work_pages(work_id: str, pages: list[WorkPageRow]) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM pages WHERE work_id = ?", (work_id,))
        for page in pages:
            connection.execute(
                """
                INSERT INTO pages (
                    work_id, page_index, image_filename, thumb_filename, width, height
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    as_int(page.get("page_index", 0), 0),
                    str(page.get("image_filename", "")),
                    page.get("thumb_filename"),
                    page.get("width"),
                    page.get("height"),
                ),
            )
    sync_work_metadata_toml(work_id)


def list_works(filters: dict[str, str]) -> list[WorkListItem]:
    where: list[str] = []
    params: list[object] = []

    include_mature = bool(as_int(filters.get("include_mature", "0"), 0))
    include_explicit = bool(as_int(filters.get("include_explicit", "0"), 0))
    if not include_mature:
        where.append("w.rating <> ?")
        params.append("Mature")
    if not include_explicit:
        where.append("w.rating <> ?")
        params.append("Explicit")

    search = filters.get("q", "").strip()
    if search:
        fts_tokens = _FTS_TOKEN_RE.findall(search)
        if fts_tokens:
            fts_query = " ".join(f"{token}*" for token in fts_tokens)
            where.append("w.rowid IN (SELECT ws.rowid FROM works_search ws WHERE works_search MATCH ?)")
            params.append(fts_query)
        else:
            where.append("1 = 0")

    tag_terms = _csv_terms(filters.get("tag", ""))
    if tag_terms:
        per_term_clauses: list[str] = []
        for term in tag_terms:
            per_term_clauses.append("(t.slug = ? OR lower(t.name) LIKE ? OR lower(t.slug) LIKE ?)")
            normalized_term = term.lower()
            term_like = f"%{normalized_term}%"
            params.append(slugify(term))
            params.append(term_like)
            params.append(term_like)
        where.append(
            "EXISTS (SELECT 1 FROM work_tags wt JOIN tags t ON t.id = wt.tag_id "
            "WHERE wt.work_id = w.id AND (" + " OR ".join(per_term_clauses) + "))"
        )

    fandom_terms = _csv_terms(filters.get("fandom", ""))
    if fandom_terms:
        per_term_clauses = []
        for term in fandom_terms:
            per_term_clauses.append("(t.slug = ? OR lower(t.name) LIKE ? OR lower(t.slug) LIKE ?)")
            normalized_term = term.lower()
            term_like = f"%{normalized_term}%"
            params.append(slugify(term))
            params.append(term_like)
            params.append(term_like)
        where.append(
            "EXISTS (SELECT 1 FROM work_tags wt JOIN tags t ON t.id = wt.tag_id "
            "WHERE wt.work_id = w.id AND t.type = 'fandom' AND (" + " OR ".join(per_term_clauses) + "))"
        )

    user_terms = _csv_terms(filters.get("user", ""))
    if user_terms:
        per_term_clauses = []
        for term in user_terms:
            normalized_term = term.lower()
            term_like = f"%{normalized_term}%"
            per_term_clauses.append("(lower(w.uploader_username) LIKE ? OR lower(COALESCE(u.display_name, '')) LIKE ?)")
            params.append(term_like)
            params.append(term_like)
        where.append("(" + " OR ".join(per_term_clauses) + ")")

    sort = filters.get("sort", "newest")
    order_by = "w.updated_at DESC"
    if sort == "oldest":
        order_by = "w.created_at ASC"
    elif sort == "title_asc":
        order_by = "w.title COLLATE NOCASE ASC"
    elif sort == "title_desc":
        order_by = "w.title COLLATE NOCASE DESC"

    sql = """
        SELECT w.id, w.slug, w.title, w.summary, w.status, w.rating, w.warnings,
               w.page_count, w.cover_page_index, w.updated_at,
               p.image_filename AS cover_image_filename,
               p.thumb_filename AS cover_thumb_filename
        FROM works w
        LEFT JOIN pages p
            ON p.work_id = w.id AND p.page_index = w.cover_page_index
        LEFT JOIN users u
            ON lower(u.username) = lower(w.uploader_username)
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += f" ORDER BY {order_by}, w.id ASC"

    limit = as_int(filters.get("limit", 120), 120)
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    offset = as_int(filters.get("offset", 0), 0)
    if offset < 0:
        offset = 0

    sql += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_connection() as connection:
        works_search_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'works_search'"
        ).fetchone()
        if works_search_exists is None:
            raise RuntimeError("works_search index is required. Run database migrations before serving search.")
        rows = connection.execute(sql, params).fetchall()
        works: list[WorkListItem] = []
        for row in rows:
            item: WorkListItem = {
                "id": str(row["id"]),
                "slug": str(row["slug"]),
                "title": str(row["title"]),
                "summary": str(row["summary"]),
                "status": str(row["status"]),
                "rating": str(row["rating"]),
                "warnings": str(row["warnings"]),
                "page_count": int(row["page_count"]),
                "cover_page_index": int(row["cover_page_index"]),
                "updated_at": str(row["updated_at"]),
            }
            cover_image = row["cover_image_filename"]
            cover_thumb = row["cover_thumb_filename"]
            if cover_image is not None:
                item["cover_image_filename"] = str(cover_image)
            if cover_thumb is not None:
                item["cover_thumb_filename"] = str(cover_thumb)
            works.append(item)
        return works


def list_works_by_uploader(username: str) -> list[WorkListItem]:
    if not username.strip():
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
             SELECT w.id, w.slug, w.title, w.summary, w.status, w.rating, w.warnings,
                 w.page_count, w.cover_page_index, w.updated_at, w.uploader_username,
                   p.image_filename AS cover_image_filename,
                   p.thumb_filename AS cover_thumb_filename
            FROM works w
            LEFT JOIN pages p
                ON p.work_id = w.id AND p.page_index = w.cover_page_index
            WHERE w.uploader_username = ?
            ORDER BY w.updated_at DESC
            """,
            (username.strip(),),
        ).fetchall()
    works: list[WorkListItem] = []
    for row in rows:
        item: WorkListItem = {
            "id": str(row["id"]),
            "slug": str(row["slug"]),
            "title": str(row["title"]),
            "summary": str(row["summary"]),
            "status": str(row["status"]),
            "rating": str(row["rating"]),
            "warnings": str(row["warnings"]),
            "page_count": int(row["page_count"]),
            "cover_page_index": int(row["cover_page_index"]),
            "updated_at": str(row["updated_at"]),
            "uploader_username": str(row["uploader_username"]),
        }
        cover_image = row["cover_image_filename"]
        cover_thumb = row["cover_thumb_filename"]
        if cover_image is not None:
            item["cover_image_filename"] = str(cover_image)
        if cover_thumb is not None:
            item["cover_thumb_filename"] = str(cover_thumb)
        works.append(item)
    return works


def list_work_versions(work_id: str, limit: int = 50) -> list[WorkVersionSummary]:
    if limit < 1:
        return []

    root = _versions_dir_for_work(work_id)
    if not root.exists() or not root.is_dir():
        return []

    versions: list[WorkVersionSummary] = []
    candidates = sorted(
        [path for path in root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )

    for path in candidates:
        manifest_path = path / "manifest.json"
        if not manifest_path.exists() or not manifest_path.is_file():
            continue
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        raw_map = _as_string_object_dict(raw)
        if raw_map is None:
            continue

        work_block = raw_map.get("work")
        page_count = 0
        work_block_map = _as_string_object_dict(work_block)
        if work_block_map is not None:
            page_count = as_int(work_block_map.get("page_count", 0), 0)

        versions.append(
            {
                "version_id": str(raw_map.get("version_id", path.name)),
                "created_at": str(raw_map.get("created_at", "")),
                "action": str(raw_map.get("action", "")),
                "actor": str(raw_map.get("actor", "")),
                "page_count": page_count,
            }
        )
        if len(versions) >= limit:
            break

    return versions


def get_manifest(work_id: str) -> dict[str, object] | None:
    work = get_work(work_id)
    if not work:
        return None

    with get_connection() as connection:
        pages = connection.execute(
            """
            SELECT page_index, image_filename, thumb_filename, width, height
            FROM pages
            WHERE work_id = ?
            ORDER BY page_index
            """,
            (work_id,),
        ).fetchall()

    manifest_pages: list[dict[str, object]] = []
    for page in pages:
        image_filename = str(page["image_filename"])
        thumb_value = page["thumb_filename"]
        thumb_filename = str(thumb_value) if thumb_value is not None else image_filename
        work_id_quoted = quote(work_id, safe="")
        image_key = f"{work_id_quoted}/pages/{quote(image_filename, safe='/')}"
        thumb_key = f"{work_id_quoted}/thumbs/{quote(thumb_filename, safe='/')}"
        manifest_pages.append(
            {
                "index": int(page["page_index"]),
                "image_url": media_public_path_from_key(image_key),
                "thumb_url": media_public_path_from_key(thumb_key),
                "width": page["width"],
                "height": page["height"],
            }
        )

    work["pages"] = manifest_pages
    work["chapters"] = list_work_chapters(work_id)
    versions = list_work_versions(work_id, limit=1)
    work["current_version_id"] = versions[0]["version_id"] if versions else ""
    return work


def list_work_page_rows(work_id: str) -> list[WorkPageRow]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT page_index, image_filename, thumb_filename, width, height
            FROM pages
            WHERE work_id = ?
            ORDER BY page_index
            """,
            (work_id,),
        ).fetchall()
    page_rows: list[WorkPageRow] = []
    for row in rows:
        page_rows.append(
            {
                "page_index": as_int(row["page_index"], 0),
                "image_filename": str(row["image_filename"]),
                "thumb_filename": (str(row["thumb_filename"]) if row["thumb_filename"] is not None else None),
                "width": (as_int(row["width"], 0) if row["width"] is not None else None),
                "height": (as_int(row["height"], 0) if row["height"] is not None else None),
            }
        )
    return page_rows


def list_work_chapter_members(chapter_id: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT page_image_filename
            FROM work_chapter_pages
            WHERE chapter_id = ?
            ORDER BY position
            """,
            (chapter_id,),
        ).fetchall()
    return [str(row["page_image_filename"]) for row in rows]


def create_work_version_snapshot(
    work_id: str,
    *,
    action: str,
    actor: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object] | None:
    work = get_work(work_id)
    if not work:
        return None

    pages = list_work_page_rows(work_id)
    chapters = list_work_chapters(work_id)
    chapters_with_members: list[dict[str, object]] = []
    for chapter in chapters:
        chapter_copy: dict[str, object] = {
            "id": chapter["id"],
            "chapter_index": chapter["chapter_index"],
            "title": chapter["title"],
            "start_page": chapter["start_page"],
            "end_page": chapter["end_page"],
            "created_at": chapter["created_at"],
        }
        chapter_id = chapter["id"]
        chapter_copy["members"] = list_work_chapter_members(chapter_id)
        chapters_with_members.append(chapter_copy)

    version_id = _new_version_id()
    created_at = _utc_now_iso()
    version_dir = _versions_dir_for_work(work_id) / version_id
    version_dir.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, object] = {
        "version_id": version_id,
        "created_at": created_at,
        "work_id": work_id,
        "action": action,
        "actor": actor if actor else "",
        "details": details if details else {},
        "work": {
            "id": str(work.get("id", work_id)),
            "slug": str(work.get("slug", "")),
            "title": str(work.get("title", "Untitled")),
            "rating": str(work.get("rating", "Not Rated")),
            "status": str(work.get("status", "in_progress")),
            "cover_page_index": as_int(work.get("cover_page_index", 1), 1),
            "page_count": as_int(work.get("page_count", 0), 0),
            "updated_at": str(work.get("updated_at", "")),
        },
        "pages": [dict(page) for page in pages],
        "chapters": chapters_with_members,
    }

    manifest_path = version_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return manifest


def get_work_version_manifest(work_id: str, version_id: str) -> dict[str, object] | None:
    if not version_id or "/" in version_id or "\\" in version_id:
        return None
    manifest_path = _versions_dir_for_work(work_id) / version_id / "manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _as_string_object_dict(raw)


def get_page_files(work_id: str, page_index: int) -> dict[str, str] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT image_filename, thumb_filename FROM pages WHERE work_id = ? AND page_index = ?",
            (work_id, page_index),
        ).fetchone()
        if not row:
            return None
        return {"image": row["image_filename"], "thumb": row["thumb_filename"]}


def list_work_page_image_names(work_id: str) -> list[str]:
    return [row["image_filename"] for row in list_work_page_rows(work_id)]


def replace_work_chapter_members(chapter_id: int, page_image_filenames: list[str]) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM work_chapter_pages WHERE chapter_id = ?",
            (chapter_id,),
        )
        for position, filename in enumerate(page_image_filenames, start=1):
            connection.execute(
                """
                INSERT INTO work_chapter_pages (chapter_id, page_image_filename, position)
                VALUES (?, ?, ?)
                """,
                (chapter_id, filename, position),
            )
    work_id = _work_id_for_chapter(chapter_id)
    if work_id:
        sync_work_metadata_toml(work_id)


def add_work_chapter(
    work_id: str,
    title: str,
    start_page: int,
    end_page: int,
) -> dict[str, object]:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(chapter_index), 0) + 1 AS next_idx FROM work_chapters WHERE work_id = ?",
            (work_id,),
        ).fetchone()
        next_idx = int(row["next_idx"]) if row else 1
        cursor = connection.execute(
            """
            INSERT INTO work_chapters (work_id, chapter_index, title, start_page, end_page)
            VALUES (?, ?, ?, ?, ?)
            """,
            (work_id, next_idx, title, start_page, end_page),
        )
        chapter_id = int(cursor.lastrowid if cursor.lastrowid else 0)

    page_images = list_work_page_image_names(work_id)
    selected = page_images[max(0, start_page - 1) : max(0, end_page)]
    replace_work_chapter_members(chapter_id, selected)

    return {
        "id": chapter_id,
        "chapter_index": next_idx,
        "title": title,
        "start_page": start_page,
        "end_page": end_page,
    }


def update_work_chapter(
    work_id: str,
    chapter_id: int,
    title: str,
    start_page: int,
    end_page: int,
) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE work_chapters
            SET title = ?, start_page = ?, end_page = ?
            WHERE work_id = ? AND id = ?
            """,
            (title, start_page, end_page, work_id, chapter_id),
        )
    if cursor.rowcount > 0:
        sync_work_metadata_toml(work_id)
    return cursor.rowcount > 0


def delete_work_chapter(work_id: str, chapter_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM work_chapters WHERE work_id = ? AND id = ?",
            (work_id, chapter_id),
        )
        if cursor.rowcount < 1:
            return False

        rows = connection.execute(
            "SELECT id FROM work_chapters WHERE work_id = ? ORDER BY chapter_index, id",
            (work_id,),
        ).fetchall()
        for idx, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE work_chapters SET chapter_index = ? WHERE id = ?",
                (idx, int(row["id"])),
            )
    sync_work_metadata_toml(work_id)
    return True


def save_progress(work_id: str, user_id: str, page_index: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO reading_progress (work_id, user_id, page_index)
            VALUES (?, ?, ?)
            ON CONFLICT(work_id, user_id) DO UPDATE SET
                page_index = excluded.page_index,
                updated_at = CURRENT_TIMESTAMP
            """,
            (work_id, user_id, page_index),
        )


def load_progress(work_id: str, user_id: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT page_index FROM reading_progress WHERE work_id = ? AND user_id = ?",
            (work_id, user_id),
        ).fetchone()
        if not row:
            return 1
        return int(row["page_index"])


def delete_work(work_id: str) -> bool:
    work = get_work(work_id)
    if not work:
        return False

    page_rows = list_work_page_rows(work_id)

    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM works WHERE id = ?", (work_id,))
        if cursor.rowcount < 1:
            return False

    media_service = get_media_service()
    media_keys_to_delete: set[str] = set()

    for page in page_rows:
        image_name = str(page.get("image_filename", "")).strip()
        if image_name:
            media_keys_to_delete.add(media_service.comic_page_key(work_id, image_name))

        thumb_name_obj = page.get("thumb_filename")
        thumb_name = str(thumb_name_obj).strip() if thumb_name_obj is not None else ""
        if thumb_name:
            media_keys_to_delete.add(media_service.comic_thumb_key(work_id, thumb_name))

    cbz_path_text = str(work.get("cbz_path", "")).strip()
    if cbz_path_text:
        cbz_name = ""
        if cbz_path_text.startswith("http://") or cbz_path_text.startswith("https://"):
            cbz_name = Path(urlsplit(cbz_path_text).path).name
        else:
            cbz_name = Path(cbz_path_text).name

        if cbz_name:
            raw_name = cbz_name.strip()
            encoded_name = quote(raw_name, safe="")
            for filename in {raw_name, encoded_name}:
                if filename:
                    media_keys_to_delete.add(f"cbz/{filename}")
                    media_keys_to_delete.add(f"cbz/{filename}.meta.json")
                    media_keys_to_delete.add(f"{quote(work_id.strip(), safe='')}/downloads/{filename}")

        parsed_path = urlsplit(cbz_path_text).path if "://" in cbz_path_text else cbz_path_text
        static_tail = ""
        if "/static/" in parsed_path:
            static_tail = parsed_path.split("/static/", 1)[1].strip("/")
        elif parsed_path.startswith("static/"):
            static_tail = parsed_path[len("static/") :].strip("/")

        if static_tail:
            media_keys_to_delete.add(static_tail)
            if static_tail.endswith(".cbz"):
                media_keys_to_delete.add(f"{static_tail}.meta.json")

    for media_key in media_keys_to_delete:
        try:
            media_service.delete(media_key)
        except Exception:
            pass

    if cbz_path_text:
        cbz_path = Path(cbz_path_text)
        try:
            cbz_resolved = cbz_path.resolve()
            _ = cbz_resolved.relative_to(CBZ_DIR.resolve())
            delete_file(cbz_resolved, missing_ok=True)
        except (OSError, ValueError):
            pass

    work_dir = WORKS_DIR / work_id
    try:
        delete_tree(work_dir, ignore_errors=True)
    except OSError:
        pass

    return True
