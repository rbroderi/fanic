from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict

import tomli_w

from fanic.db import get_connection
from fanic.paths import CBZ_DIR, WORKS_DIR
from fanic.utils import slugify

TAG_FIELD_TO_TYPE = {
    "fandoms": "fandom",
    "relationships": "relationship",
    "characters": "character",
    "freeform_tags": "freeform",
}


class WorkComment(TypedDict):
    id: int
    username: str
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
    updated_at: str
    uploader_username: NotRequired[str]


class WorkVersionSummary(TypedDict):
    version_id: str
    created_at: str
    action: str
    actor: str
    page_count: int


def _versions_dir_for_work(work_id: str) -> Path:
    return WORKS_DIR / work_id / "versions"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_version_id() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S_%fZ")


def _strip_none_values(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _strip_none_values(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_strip_none_values(item) for item in value]
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


def sync_work_metadata_toml(work_id: str) -> None:
    work = get_work(work_id)
    if not work:
        return

    tags: list[dict[str, object]] = []
    raw_tags = work.get("tags", [])
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, dict):
                tags.append(
                    {
                        "name": str(tag.get("name", "")),
                        "slug": str(tag.get("slug", "")),
                        "type": str(tag.get("type", "")),
                    }
                )

    raw_chapters = list_work_chapters(work_id)
    chapters: list[dict[str, object]] = []
    for chapter in raw_chapters:
        chapter_id = int(chapter.get("id", 0) or 0)
        chapters.append(
            {
                "id": chapter_id,
                "chapter_index": int(chapter.get("chapter_index", 0) or 0),
                "title": str(chapter.get("title", "")),
                "start_page": int(chapter.get("start_page", 1) or 1),
                "end_page": int(chapter.get("end_page", 1) or 1),
                "created_at": chapter.get("created_at"),
            }
        )

    creators = work.get("creators", [])
    if not isinstance(creators, list):
        creators = []

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
            "cover_page_index": int(work.get("cover_page_index", 1) or 1),
            "page_count": int(work.get("page_count", 0) or 0),
            "cbz_path": str(work.get("cbz_path", "")),
            "uploader_username": work.get("uploader_username"),
            "created_at": work.get("created_at"),
            "updated_at": work.get("updated_at"),
            "last_metadata_editor": work.get("last_metadata_editor"),
            "last_metadata_edited_at": work.get("last_metadata_edited_at"),
            "last_metadata_edited_by_admin": bool(
                int(work.get("last_metadata_edited_by_admin", 0) or 0)
            ),
        },
        "tags": tags,
        "chapters": chapters,
        "kudos": {"count": work_kudos_count(work_id)},
        "comments": list_work_comments(work_id),
    }

    clean_payload = _strip_none_values(payload)
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
            (work_dir / legacy_name).unlink(missing_ok=True)
        except OSError:
            pass


def work_is_explicit(work: Mapping[str, object]) -> bool:
    return str(work.get("rating", "")).strip().lower() == "explicit"


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


def set_user_prefers_explicit(username: str, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (username, view_explicit_rated)
            VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET
                view_explicit_rated = excluded.view_explicit_rated,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, 1 if enabled else 0),
        )


def can_view_work(username: str | None, work: Mapping[str, object]) -> bool:
    if work_is_explicit(work):
        return user_prefers_explicit(username)
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


def list_work_comments(work_id: str) -> list[WorkComment]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, username, chapter_number, body, created_at
            FROM work_comments
            WHERE work_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (work_id,),
        ).fetchall()
    comments: list[WorkComment] = []
    for row in rows:
        chapter_number_raw = row["chapter_number"]
        chapter_number = (
            int(chapter_number_raw) if chapter_number_raw is not None else None
        )
        comments.append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "chapter_number": chapter_number,
                "body": str(row["body"]),
                "created_at": str(row["created_at"]),
            }
        )
    return comments


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


def work_kudos_count(work_id: str) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM work_kudos WHERE work_id = ?",
            (work_id,),
        ).fetchone()
    if not row:
        return 0
    return int(row["count"])


def has_user_kudoed_work(work_id: str, username: str | None) -> bool:
    if not username:
        return False
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM work_kudos WHERE work_id = ? AND username = ?",
            (work_id, username),
        ).fetchone()
    return bool(row)


def list_tag_names(tag_type: str, limit: int = 200) -> list[str]:
    if limit < 1:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM tags
            WHERE type = ?
            ORDER BY name COLLATE NOCASE
            LIMIT ?
            """,
            (tag_type, int(limit)),
        ).fetchall()
    return [str(row["name"]) for row in rows]


def upsert_work(work: dict[str, object]) -> None:
    warnings_value = work.get("warnings", "No Archive Warnings Apply")
    if isinstance(warnings_value, list):
        warnings_text = ", ".join(
            str(item) for item in warnings_value if str(item).strip()
        )
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
                int(work.get("cover_page_index", 1)),
                int(work["page_count"]),
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


def update_work_metadata(
    work_id: str,
    metadata: dict[str, object],
    editor_username: str,
    edited_by_admin: bool,
) -> None:
    warnings_value = metadata.get("warnings", "")
    if isinstance(warnings_value, list):
        warnings_text = ", ".join(
            str(item) for item in warnings_value if str(item).strip()
        )
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
                metadata.get("series", "") or None,
                metadata.get("series_index"),
                metadata.get("published_at", "") or None,
                editor_username,
                1 if edited_by_admin else 0,
                work_id,
            ),
        )

    replace_work_tags(work_id, metadata)
    sync_work_metadata_toml(work_id)


def replace_work_pages(work_id: str, pages: list[dict[str, object]]) -> None:
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
                    int(page["page_index"]),
                    page["image_filename"],
                    page.get("thumb_filename"),
                    page.get("width"),
                    page.get("height"),
                ),
            )
    sync_work_metadata_toml(work_id)


def _ensure_tag(name: str, tag_type: str) -> int:
    slug = slugify(name)
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM tags WHERE slug = ?", (slug,)
        ).fetchone()
        if existing:
            return int(existing["id"])

        cursor = connection.execute(
            "INSERT INTO tags (slug, name, type) VALUES (?, ?, ?)",
            (slug, name, tag_type),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to insert tag")
        return int(cursor.lastrowid)


def replace_work_tags(work_id: str, metadata: dict[str, object]) -> None:
    tag_pairs: list[tuple[str, str]] = []

    for field_name, tag_type in TAG_FIELD_TO_TYPE.items():
        for name in metadata.get(field_name, []):
            if name:
                tag_pairs.append((name, tag_type))

    rating = metadata.get("rating")
    if rating:
        tag_pairs.append((rating, "rating"))

    warnings = metadata.get("warnings", [])
    if isinstance(warnings, str):
        warnings = [warnings]
    for warning in warnings:
        if warning:
            tag_pairs.append((warning, "archive_warning"))

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM work_tags WHERE work_id = ?",
            (work_id,),
        )

    for name, tag_type in tag_pairs:
        tag_id = _ensure_tag(name, tag_type)
        with get_connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO work_tags (work_id, tag_id) VALUES (?, ?)",
                (work_id, tag_id),
            )
    sync_work_metadata_toml(work_id)


def list_works(filters: dict[str, str]) -> list[WorkListItem]:
    where = []
    params: list[object] = []

    search = filters.get("q")
    if search:
        where.append("(w.title LIKE ? OR w.summary LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    status = filters.get("status")
    if status:
        where.append("w.status = ?")
        params.append(status)

    rating = filters.get("rating")
    if rating:
        where.append("w.rating = ?")
        params.append(rating)

    tag = filters.get("tag")
    if tag:
        where.append(
            "EXISTS (SELECT 1 FROM work_tags wt JOIN tags t ON t.id = wt.tag_id WHERE wt.work_id = w.id AND t.slug = ?)"
        )
        params.append(slugify(tag))

    fandom = filters.get("fandom")
    if fandom:
        where.append(
            "EXISTS (SELECT 1 FROM work_tags wt JOIN tags t ON t.id = wt.tag_id WHERE wt.work_id = w.id AND t.type = 'fandom' AND t.slug = ?)"
        )
        params.append(slugify(fandom))

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
               w.page_count, w.cover_page_index, w.updated_at
        FROM works w
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += f" ORDER BY {order_by}, w.id ASC"

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()
        works: list[WorkListItem] = []
        for row in rows:
            works.append(
                {
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
            )
        return works


def list_works_by_uploader(username: str) -> list[WorkListItem]:
    if not username.strip():
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, slug, title, summary, status, rating, warnings,
                   page_count, cover_page_index, updated_at, uploader_username
            FROM works
            WHERE uploader_username = ?
            ORDER BY updated_at DESC
            """,
            (username.strip(),),
        ).fetchall()
    works: list[WorkListItem] = []
    for row in rows:
        works.append(
            {
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
        )
    return works


def get_work(work_id: str) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM works WHERE id = ?", (work_id,)
        ).fetchone()
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

    work["pages"] = [
        {
            "index": int(page["page_index"]),
            "image_url": f"/api/works/{work_id}/pages/{int(page['page_index'])}/image",
            "thumb_url": f"/api/works/{work_id}/pages/{int(page['page_index'])}/thumb",
            "width": page["width"],
            "height": page["height"],
        }
        for page in pages
    ]
    work["chapters"] = list_work_chapters(work_id)
    versions = list_work_versions(work_id, limit=1)
    work["current_version_id"] = versions[0]["version_id"] if versions else ""
    return work


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
        chapter_copy = dict(chapter)
        chapter_id = int(chapter_copy.get("id", 0) or 0)
        chapter_copy["members"] = list_work_chapter_members(chapter_id)
        chapters_with_members.append(chapter_copy)

    version_id = _new_version_id()
    created_at = _utc_now_iso()
    version_dir = _versions_dir_for_work(work_id) / version_id
    version_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "version_id": version_id,
        "created_at": created_at,
        "work_id": work_id,
        "action": action,
        "actor": actor or "",
        "details": details or {},
        "work": {
            "id": str(work.get("id", work_id)),
            "slug": str(work.get("slug", "")),
            "title": str(work.get("title", "Untitled")),
            "rating": str(work.get("rating", "Not Rated")),
            "status": str(work.get("status", "in_progress")),
            "cover_page_index": int(work.get("cover_page_index", 1) or 1),
            "page_count": int(work.get("page_count", 0) or 0),
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


def get_work_version_manifest(
    work_id: str, version_id: str
) -> dict[str, object] | None:
    if not version_id or "/" in version_id or "\\" in version_id:
        return None
    manifest_path = _versions_dir_for_work(work_id) / version_id / "manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


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
        if not isinstance(raw, dict):
            continue

        work_block = raw.get("work")
        page_count = 0
        if isinstance(work_block, dict):
            try:
                page_count = int(work_block.get("page_count", 0) or 0)
            except (TypeError, ValueError):
                page_count = 0

        versions.append(
            {
                "version_id": str(raw.get("version_id", path.name)),
                "created_at": str(raw.get("created_at", "")),
                "action": str(raw.get("action", "")),
                "actor": str(raw.get("actor", "")),
                "page_count": page_count,
            }
        )
        if len(versions) >= limit:
            break

    return versions


def get_page_files(work_id: str, page_index: int) -> dict[str, str] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT image_filename, thumb_filename FROM pages WHERE work_id = ? AND page_index = ?",
            (work_id, page_index),
        ).fetchone()
        if not row:
            return None
        return {"image": row["image_filename"], "thumb": row["thumb_filename"]}


def list_work_page_rows(work_id: str) -> list[dict[str, object]]:
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
    return [dict(row) for row in rows]


def list_work_page_image_names(work_id: str) -> list[str]:
    return [str(row.get("image_filename", "")) for row in list_work_page_rows(work_id)]


def list_work_chapters(work_id: str) -> list[dict[str, object]]:
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
    return [dict(row) for row in rows]


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
        chapter_id = int(cursor.lastrowid or 0)

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


def replace_work_chapter_members(
    chapter_id: int, page_image_filenames: list[str]
) -> None:
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

    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM works WHERE id = ?", (work_id,))
        if cursor.rowcount < 1:
            return False

    cbz_path_text = str(work.get("cbz_path", "")).strip()
    if cbz_path_text:
        cbz_path = Path(cbz_path_text)
        try:
            cbz_resolved = cbz_path.resolve()
            _ = cbz_resolved.relative_to(CBZ_DIR.resolve())
            cbz_resolved.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    work_dir = WORKS_DIR / work_id
    try:
        shutil.rmtree(work_dir, ignore_errors=True)
    except OSError:
        pass

    return True
