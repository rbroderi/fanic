from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Literal
from typing import NotRequired
from typing import TypedDict
from typing import cast

import tomli_w

from fanic.db import get_connection
from fanic.settings import CBZ_DIR
from fanic.settings import WORKS_DIR
from fanic.utils import slugify

TAG_FIELD_TO_TYPE = {
    "fandoms": "fandom",
    "relationships": "relationship",
    "characters": "character",
    "freeform_tags": "freeform",
}

UserRole = Literal["superadmin", "admin", "user", "guest"]
PRIVILEGED_USER_ROLES: set[UserRole] = {"superadmin", "admin"}
MANAGED_USER_ROLES: set[UserRole] = {"superadmin", "admin", "user"}


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


class UserThemePreference(TypedDict):
    enabled: bool
    toml_text: str


class LocalUserRow(TypedDict):
    username: str
    display_name: str
    email: str | None
    role: UserRole
    active: bool
    created_at: str


class RecentReadingHistoryRow(TypedDict):
    work_id: str
    work_title: str
    page_index: int
    updated_at: str


def _normalize_user_role(role: object) -> UserRole:
    normalized = str(role).strip().lower()
    if normalized == "superadmin":
        return "superadmin"
    if normalized == "admin":
        return "admin"
    if normalized == "user":
        return "user"
    return "guest"


def _validate_managed_role(role: UserRole) -> UserRole:
    normalized_role = _normalize_user_role(role)
    if normalized_role not in MANAGED_USER_ROLES:
        raise ValueError("Role must be one of: superadmin, admin, user")
    return normalized_role


def upsert_user(
    user_id: str,
    username: str,
    *,
    display_name: str,
    email: str | None,
    active: bool,
    role: UserRole,
) -> None:
    normalized_role = _validate_managed_role(role)
    normalized_email = email.strip() if isinstance(email, str) else ""
    stored_email = normalized_email if normalized_email else None

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, display_name, email, active, role)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                email = excluded.email,
                active = excluded.active,
                role = excluded.role
            """,
            (
                user_id,
                username,
                display_name,
                stored_email,
                1 if active else 0,
                normalized_role,
            ),
        )


def ensure_local_user(username: str, *, role: UserRole = "user") -> None:
    normalized_username = username.strip()
    if not normalized_username:
        return
    upsert_user(
        normalized_username,
        normalized_username,
        display_name=normalized_username,
        email=None,
        active=True,
        role=role,
    )


def create_user(
    username: str,
    *,
    display_name: str,
    email: str | None = None,
    role: UserRole = "user",
    active: bool = True,
) -> None:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_display_name = display_name.strip()
    if not normalized_display_name:
        raise ValueError("display_name must not be empty")

    normalized_role = _validate_managed_role(role)
    normalized_email = email.strip() if isinstance(email, str) else ""
    stored_email = normalized_email if normalized_email else None

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, display_name, email, active, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_username,
                normalized_username,
                normalized_display_name,
                stored_email,
                1 if active else 0,
                normalized_role,
            ),
        )


def set_user_role(username: str, role: UserRole) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    normalized_role = _validate_managed_role(role)
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET role = ? WHERE username = ?",
            (normalized_role, normalized_username),
        )
    return cursor.rowcount > 0


def set_user_active(username: str, active: bool) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET active = ? WHERE username = ?",
            (1 if active else 0, normalized_username),
        )
    return cursor.rowcount > 0


def get_user_role(username: str | None) -> UserRole:
    normalized_username = username.strip() if isinstance(username, str) else ""
    if not normalized_username:
        return "guest"

    with get_connection() as connection:
        row = connection.execute(
            "SELECT role, active FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()

    if not row:
        return "guest"
    if not bool(int(row["active"])):
        return "guest"
    return _normalize_user_role(row["role"])


def get_local_user(username: str) -> LocalUserRow | None:
    normalized_username = username.strip()
    if not normalized_username:
        return None

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT username, display_name, email, role, active, created_at
            FROM users
            WHERE username = ?
            """,
            (normalized_username,),
        ).fetchone()

    if not row:
        return None

    return {
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "email": str(row["email"]) if row["email"] is not None else None,
        "role": _normalize_user_role(row["role"]),
        "active": bool(int(row["active"])),
        "created_at": str(row["created_at"]),
    }


def count_local_users() -> int:
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0


def list_local_users(*, offset: int = 0, limit: int = 0) -> list[LocalUserRow]:
    sql = """
        SELECT username, display_name, email, role, active, created_at
        FROM users
        ORDER BY
            CASE role
                WHEN 'superadmin' THEN 0
                WHEN 'admin' THEN 1
                WHEN 'user' THEN 2
                ELSE 3
            END,
            username COLLATE NOCASE ASC
    """
    params: list[int] = []
    if limit > 0:
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    return [
        {
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "email": str(row["email"]) if row["email"] is not None else None,
            "role": _normalize_user_role(row["role"]),
            "active": bool(int(row["active"])),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


def delete_user(username: str) -> bool:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("username must not be empty")

    with get_connection() as connection:
        connection.execute(
            "DELETE FROM user_preferences WHERE username = ?",
            (normalized_username,),
        )
        cursor = connection.execute(
            "DELETE FROM users WHERE username = ?",
            (normalized_username,),
        )
    return cursor.rowcount > 0


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


class ContentReportRow(TypedDict):
    id: int
    work_id: str | None
    work_title: str
    issue_type: str
    status: str
    reason: str
    reporter_name: str
    reporter_email: str
    claimed_url: str
    evidence_url: str
    details: str
    reporter_username: str
    source_path: str
    created_at: str


def _versions_dir_for_work(work_id: str) -> Path:
    return WORKS_DIR / work_id / "versions"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_version_id() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%S_%fZ")


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
            "cover_page_index": _to_int(work.get("cover_page_index", 1), 1),
            "page_count": _to_int(work.get("page_count", 0), 0),
            "cbz_path": str(work.get("cbz_path", "")),
            "uploader_username": work.get("uploader_username"),
            "created_at": work.get("created_at"),
            "updated_at": work.get("updated_at"),
            "last_metadata_editor": work.get("last_metadata_editor"),
            "last_metadata_edited_at": work.get("last_metadata_edited_at"),
            "last_metadata_edited_by_admin": bool(
                _to_int(work.get("last_metadata_edited_by_admin", 0), 0)
            ),
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
            INSERT INTO user_preferences (username, view_explicit_rated, custom_theme_enabled, custom_theme_toml)
            VALUES (?, ?, 0, NULL)
            ON CONFLICT(username) DO UPDATE SET
                view_explicit_rated = excluded.view_explicit_rated,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, 1 if enabled else 0),
        )


def get_user_theme_preference(username: str | None) -> UserThemePreference:
    if not username:
        return {"enabled": False, "toml_text": ""}

    with get_connection() as connection:
        row = connection.execute(
            "SELECT custom_theme_enabled, custom_theme_toml FROM user_preferences WHERE username = ?",
            (username,),
        ).fetchone()

    if not row:
        return {"enabled": False, "toml_text": ""}

    return {
        "enabled": bool(int(row["custom_theme_enabled"])),
        "toml_text": str(row["custom_theme_toml"] if row["custom_theme_toml"] else ""),
    }


def set_user_theme_preference(
    username: str,
    *,
    enabled: bool,
    toml_text: str | None,
) -> None:
    existing = get_user_theme_preference(username)
    resolved_toml_text = toml_text if toml_text is not None else existing["toml_text"]

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_preferences (username, view_explicit_rated, custom_theme_enabled, custom_theme_toml)
            VALUES (?, 0, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                custom_theme_enabled = excluded.custom_theme_enabled,
                custom_theme_toml = excluded.custom_theme_toml,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                username,
                1 if enabled else 0,
                resolved_toml_text,
            ),
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


def add_dmca_report(
    *,
    work_id: str | None,
    work_title: str,
    issue_type: str,
    reporter_name: str,
    reporter_email: str,
    reason: str,
    claimed_url: str,
    evidence_url: str,
    details: str,
    reporter_username: str | None,
    source_path: str,
) -> int:
    normalized_work_id = work_id.strip() if work_id else ""
    stored_work_id = normalized_work_id if normalized_work_id else None
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO dmca_reports (
                work_id,
                work_title,
                issue_type,
                reporter_name,
                reporter_email,
                reason,
                claimed_url,
                evidence_url,
                details,
                reporter_username,
                source_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored_work_id,
                work_title,
                issue_type,
                reporter_name,
                reporter_email,
                reason,
                claimed_url,
                evidence_url,
                details,
                reporter_username,
                source_path,
            ),
        )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to persist DMCA report")
    return int(cursor.lastrowid)


def list_content_reports(
    *,
    work_id: str,
    issue_type: str,
    status: str,
    start_date: str,
    end_date: str,
    limit: int = 250,
) -> list[ContentReportRow]:
    where: list[str] = []
    params: list[object] = []

    normalized_work_id = work_id.strip()
    if normalized_work_id:
        where.append("work_id = ?")
        params.append(normalized_work_id)

    normalized_issue_type = issue_type.strip()
    if normalized_issue_type:
        where.append("issue_type = ?")
        params.append(normalized_issue_type)

    normalized_status = status.strip()
    if normalized_status:
        where.append("status = ?")
        params.append(normalized_status)

    normalized_start_date = start_date.strip()
    if normalized_start_date:
        where.append("substr(created_at, 1, 10) >= ?")
        params.append(normalized_start_date)

    normalized_end_date = end_date.strip()
    if normalized_end_date:
        where.append("substr(created_at, 1, 10) <= ?")
        params.append(normalized_end_date)

    sql = """
        SELECT
            id,
            work_id,
            work_title,
            issue_type,
            status,
            reason,
            reporter_name,
            reporter_email,
            claimed_url,
            evidence_url,
            details,
            reporter_username,
            source_path,
            created_at
        FROM dmca_reports
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(int(limit))

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    reports: list[ContentReportRow] = []
    for row in rows:
        work_id_obj = row["work_id"]
        reporter_username_obj = row["reporter_username"]
        reports.append(
            {
                "id": int(row["id"]),
                "work_id": str(work_id_obj) if work_id_obj is not None else None,
                "work_title": str(row["work_title"]),
                "issue_type": str(row["issue_type"]),
                "status": str(row["status"]),
                "reason": str(row["reason"]),
                "reporter_name": str(row["reporter_name"]),
                "reporter_email": str(row["reporter_email"]),
                "claimed_url": str(row["claimed_url"]),
                "evidence_url": str(row["evidence_url"]),
                "details": str(row["details"]),
                "reporter_username": (
                    str(reporter_username_obj)
                    if reporter_username_obj is not None
                    else ""
                ),
                "source_path": str(row["source_path"]),
                "created_at": str(row["created_at"]),
            }
        )
    return reports


def update_content_report_status(report_id: int, status: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE dmca_reports
            SET status = ?
            WHERE id = ?
            """,
            (status, report_id),
        )
    return cursor.rowcount > 0


def delete_content_report(report_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM dmca_reports WHERE id = ?",
            (report_id,),
        )
    return cursor.rowcount > 0


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
                _to_int(work.get("cover_page_index", 1), 1),
                _to_int(work.get("page_count", 0), 0),
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
                metadata.get("published_at", "")
                if metadata.get("published_at", "")
                else None,
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
        "series": (
            existing_work.get("series_name") if existing_work.get("series_name") else ""
        ),
        "series_index": existing_work.get("series_index"),
        "published_at": (
            existing_work.get("published_at")
            if existing_work.get("published_at")
            else ""
        ),
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
                    _to_int(page.get("page_index", 0), 0),
                    str(page.get("image_filename", "")),
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
    where: list[str] = []
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
            "cover_page_index": _to_int(work.get("cover_page_index", 1), 1),
            "page_count": _to_int(work.get("page_count", 0), 0),
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
    return _as_string_object_dict(raw)


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
            page_count = _to_int(work_block_map.get("page_count", 0), 0)

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


def get_page_files(work_id: str, page_index: int) -> dict[str, str] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT image_filename, thumb_filename FROM pages WHERE work_id = ? AND page_index = ?",
            (work_id, page_index),
        ).fetchone()
        if not row:
            return None
        return {"image": row["image_filename"], "thumb": row["thumb_filename"]}


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
                "page_index": _to_int(row["page_index"], 0),
                "image_filename": str(row["image_filename"]),
                "thumb_filename": (
                    str(row["thumb_filename"])
                    if row["thumb_filename"] is not None
                    else None
                ),
                "width": (
                    _to_int(row["width"], 0) if row["width"] is not None else None
                ),
                "height": (
                    _to_int(row["height"], 0) if row["height"] is not None else None
                ),
            }
        )
    return page_rows


def list_work_page_image_names(work_id: str) -> list[str]:
    return [row["image_filename"] for row in list_work_page_rows(work_id)]


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
                "id": _to_int(row["id"], 0),
                "chapter_index": _to_int(row["chapter_index"], 0),
                "title": str(row["title"]),
                "start_page": _to_int(row["start_page"], 1),
                "end_page": _to_int(row["end_page"], 1),
                "created_at": str(row["created_at"]),
            }
        )
    return chapter_rows


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


def list_recent_reading_history(
    user_id: str,
    *,
    limit: int,
) -> list[RecentReadingHistoryRow]:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        return []

    normalized_limit = int(limit)
    if normalized_limit < 1:
        return []

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT rp.work_id, w.title, rp.page_index, rp.updated_at
            FROM reading_progress rp
            JOIN works w ON w.id = rp.work_id
            WHERE rp.user_id = ?
            ORDER BY rp.updated_at DESC
            LIMIT ?
            """,
            (normalized_user_id, normalized_limit),
        ).fetchall()

    history_rows: list[RecentReadingHistoryRow] = []
    for row in rows:
        history_rows.append(
            {
                "work_id": str(row["work_id"]),
                "work_title": str(row["title"]),
                "page_index": _to_int(row["page_index"], 1),
                "updated_at": str(row["updated_at"]),
            }
        )
    return history_rows


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
