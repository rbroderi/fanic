import json
from typing import TypedDict

from fanic.db import get_connection


class ModerationReviewItem(TypedDict):
    id: int
    content_type: str
    content_id: str
    uploader_username: str
    source_member: str
    reason_type: str
    confidence: float
    min_threshold: float
    max_threshold: float
    moderation_json: str
    status: str
    created_at: str
    reviewed_by: str
    reviewed_at: str
    review_note: str
    content_title: str
    content_href: str


def enqueue_moderation_review(
    *,
    content_type: str,
    content_id: str,
    uploader_username: str,
    reason_type: str,
    confidence: float,
    min_threshold: float,
    max_threshold: float,
    moderation_payload: dict[str, object],
    source_member: str = "",
) -> None:
    normalized_content_type = content_type.strip().lower()
    normalized_content_id = content_id.strip()
    normalized_uploader = uploader_username.strip()
    normalized_reason = reason_type.strip().lower()
    normalized_source_member = source_member.strip()

    if normalized_content_type not in {"work", "fanart"}:
        raise ValueError("content_type must be 'work' or 'fanart'")
    if not normalized_content_id:
        raise ValueError("content_id must not be empty")
    if normalized_reason not in {"explicit", "photorealistic"}:
        raise ValueError("reason_type must be 'explicit' or 'photorealistic'")

    moderation_json = json.dumps(moderation_payload, ensure_ascii=True, sort_keys=True)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO moderation_review_queue (
                content_type,
                content_id,
                uploader_username,
                source_member,
                reason_type,
                confidence,
                min_threshold,
                max_threshold,
                moderation_json,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(content_type, content_id, source_member, reason_type, status)
            DO UPDATE SET
                confidence = excluded.confidence,
                min_threshold = excluded.min_threshold,
                max_threshold = excluded.max_threshold,
                moderation_json = excluded.moderation_json,
                created_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_content_type,
                normalized_content_id,
                normalized_uploader,
                normalized_source_member,
                normalized_reason,
                float(confidence),
                float(min_threshold),
                float(max_threshold),
                moderation_json,
            ),
        )


def list_moderation_review_items(*, status: str = "pending", limit: int = 200) -> list[ModerationReviewItem]:
    normalized_status = status.strip().lower() if status.strip() else "pending"
    safe_limit = max(1, min(int(limit), 1000))

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                q.id,
                q.content_type,
                q.content_id,
                q.uploader_username,
                q.source_member,
                q.reason_type,
                q.confidence,
                q.min_threshold,
                q.max_threshold,
                q.moderation_json,
                q.status,
                q.created_at,
                COALESCE(q.reviewed_by, '') AS reviewed_by,
                COALESCE(q.reviewed_at, '') AS reviewed_at,
                COALESCE(q.review_note, '') AS review_note,
                CASE
                    WHEN q.content_type = 'work' THEN COALESCE((SELECT w.title FROM works w WHERE w.id = q.content_id), '')
                    WHEN q.content_type = 'fanart' THEN COALESCE((SELECT f.title FROM fanart_items f WHERE f.id = q.content_id), '')
                    ELSE ''
                END AS content_title
            FROM moderation_review_queue q
            WHERE q.status = ?
            ORDER BY q.created_at DESC, q.id DESC
            LIMIT ?
            """,
            (normalized_status, safe_limit),
        ).fetchall()

    result: list[ModerationReviewItem] = []
    for row in rows:
        content_type = str(row["content_type"])
        content_id = str(row["content_id"])
        content_href = (
            f"/comic/{content_id}" if content_type == "work" else f"/fanart/{row['uploader_username']}/{content_id}"
        )
        result.append(
            {
                "id": int(row["id"]),
                "content_type": content_type,
                "content_id": content_id,
                "uploader_username": str(row["uploader_username"]),
                "source_member": str(row["source_member"]),
                "reason_type": str(row["reason_type"]),
                "confidence": float(row["confidence"]),
                "min_threshold": float(row["min_threshold"]),
                "max_threshold": float(row["max_threshold"]),
                "moderation_json": str(row["moderation_json"]),
                "status": str(row["status"]),
                "created_at": str(row["created_at"]),
                "reviewed_by": str(row["reviewed_by"]),
                "reviewed_at": str(row["reviewed_at"]),
                "review_note": str(row["review_note"]),
                "content_title": str(row["content_title"]),
                "content_href": content_href,
            }
        )
    return result


def update_moderation_review_status(
    *,
    queue_id: int,
    status: str,
    reviewed_by: str,
    review_note: str = "",
) -> bool:
    normalized_status = status.strip().lower()
    if normalized_status not in {"approved", "rejected", "dismissed"}:
        raise ValueError("status must be approved, rejected, or dismissed")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE moderation_review_queue
            SET
                status = ?,
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP,
                review_note = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                normalized_status,
                reviewed_by.strip(),
                review_note.strip(),
                int(queue_id),
            ),
        )
    return cursor.rowcount > 0


def get_moderation_review_item(queue_id: int) -> ModerationReviewItem | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                q.id,
                q.content_type,
                q.content_id,
                q.uploader_username,
                q.source_member,
                q.reason_type,
                q.confidence,
                q.min_threshold,
                q.max_threshold,
                q.moderation_json,
                q.status,
                q.created_at,
                COALESCE(q.reviewed_by, '') AS reviewed_by,
                COALESCE(q.reviewed_at, '') AS reviewed_at,
                COALESCE(q.review_note, '') AS review_note,
                CASE
                    WHEN q.content_type = 'work' THEN COALESCE((SELECT w.title FROM works w WHERE w.id = q.content_id), '')
                    WHEN q.content_type = 'fanart' THEN COALESCE((SELECT f.title FROM fanart_items f WHERE f.id = q.content_id), '')
                    ELSE ''
                END AS content_title
            FROM moderation_review_queue q
            WHERE q.id = ?
            LIMIT 1
            """,
            (int(queue_id),),
        ).fetchone()

    if row is None:
        return None

    content_type = str(row["content_type"])
    content_id = str(row["content_id"])
    content_href = (
        f"/comic/{content_id}" if content_type == "work" else f"/fanart/{row['uploader_username']}/{content_id}"
    )
    return {
        "id": int(row["id"]),
        "content_type": content_type,
        "content_id": content_id,
        "uploader_username": str(row["uploader_username"]),
        "source_member": str(row["source_member"]),
        "reason_type": str(row["reason_type"]),
        "confidence": float(row["confidence"]),
        "min_threshold": float(row["min_threshold"]),
        "max_threshold": float(row["max_threshold"]),
        "moderation_json": str(row["moderation_json"]),
        "status": str(row["status"]),
        "created_at": str(row["created_at"]),
        "reviewed_by": str(row["reviewed_by"]),
        "reviewed_at": str(row["reviewed_at"]),
        "review_note": str(row["review_note"]),
        "content_title": str(row["content_title"]),
        "content_href": content_href,
    }
