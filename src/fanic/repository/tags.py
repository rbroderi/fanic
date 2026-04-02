"""tags repository domain implementation."""

from typing import TypedDict

from fanic.db import get_connection


class TagPopularityRow(TypedDict):
    tag_id: int
    slug: str
    name: str
    type: str
    attached_works: int
    seed_count: int
    usage_count: int
    effective_popularity: int


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


def list_tag_name_suggestions(
    tag_type: str,
    query: str,
    *,
    limit: int = 12,
) -> list[str]:
    if limit < 1:
        return []

    normalized_query = query.strip().lower()
    with get_connection() as connection:
        if normalized_query:
            like_query = f"%{normalized_query}%"
            prefix_query = f"{normalized_query}%"
            rows = connection.execute(
                """
                                SELECT t.name
                                FROM tags AS t
                                LEFT JOIN tag_popularity AS tp ON tp.tag_id = t.id
                                WHERE t.type = ?
                                    AND lower(t.name) LIKE ?
                ORDER BY
                                    CASE WHEN lower(t.name) LIKE ? THEN 0 ELSE 1 END,
                                    COALESCE(tp.usage_count, 0) DESC,
                                    COALESCE(tp.seed_count, 0) DESC,
                                    length(t.name) ASC,
                                    t.name COLLATE NOCASE ASC
                LIMIT ?
                """,
                (tag_type, like_query, prefix_query, int(limit)),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                                SELECT t.name
                                FROM tags AS t
                                LEFT JOIN tag_popularity AS tp ON tp.tag_id = t.id
                                WHERE t.type = ?
                                ORDER BY
                                    COALESCE(tp.usage_count, 0) DESC,
                                    COALESCE(tp.seed_count, 0) DESC,
                                    t.name COLLATE NOCASE ASC
                LIMIT ?
                """,
                (tag_type, int(limit)),
            ).fetchall()
    return [str(row["name"]) for row in rows]


def list_top_tag_popularity(
    *,
    limit: int = 50,
    tag_type: str = "",
    query: str = "",
) -> list[TagPopularityRow]:
    if limit < 1:
        return []

    where: list[str] = []
    params: list[object] = []

    normalized_type = tag_type.strip().lower()
    if normalized_type:
        where.append("t.type = ?")
        params.append(normalized_type)

    normalized_query = query.strip().lower()
    if normalized_query:
        where.append("(lower(t.name) LIKE ? OR lower(t.slug) LIKE ?)")
        like_value = f"%{normalized_query}%"
        params.extend([like_value, like_value])

    sql = """
        SELECT
            t.id AS tag_id,
            t.slug AS slug,
            t.name AS name,
            t.type AS type,
            COALESCE(tp.seed_count, 0) AS seed_count,
            COALESCE(tp.usage_count, 0) AS usage_count,
            (
                SELECT COUNT(*)
                FROM work_tags AS wt
                WHERE wt.tag_id = t.id
            ) AS attached_works
        FROM tags AS t
        LEFT JOIN tag_popularity AS tp ON tp.tag_id = t.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += """
        ORDER BY
            (COALESCE(tp.seed_count, 0) + COALESCE(tp.usage_count, 0)) DESC,
            COALESCE(tp.usage_count, 0) DESC,
            t.name COLLATE NOCASE ASC
        LIMIT ?
    """
    params.append(int(limit))

    with get_connection() as connection:
        rows = connection.execute(sql, params).fetchall()

    results: list[TagPopularityRow] = []
    for row in rows:
        seed_count = int(row["seed_count"])
        usage_count = int(row["usage_count"])
        results.append(
            {
                "tag_id": int(row["tag_id"]),
                "slug": str(row["slug"]),
                "name": str(row["name"]),
                "type": str(row["type"]),
                "attached_works": int(row["attached_works"]),
                "seed_count": seed_count,
                "usage_count": usage_count,
                "effective_popularity": seed_count + usage_count,
            }
        )
    return results


def backfill_tag_usage_counts_from_work_tags() -> int:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO tag_popularity (tag_id, seed_count, usage_count)
            SELECT
                t.id,
                COALESCE(tp.seed_count, 0),
                COALESCE(usage_counts.usage_count, 0)
            FROM tags AS t
            LEFT JOIN tag_popularity AS tp ON tp.tag_id = t.id
            LEFT JOIN (
                SELECT wt.tag_id AS tag_id, COUNT(*) AS usage_count
                FROM work_tags AS wt
                GROUP BY wt.tag_id
            ) AS usage_counts ON usage_counts.tag_id = t.id
            ON CONFLICT(tag_id) DO UPDATE SET
                seed_count = excluded.seed_count,
                usage_count = excluded.usage_count,
                updated_at = CURRENT_TIMESTAMP
            """
        )
        row = connection.execute("SELECT COUNT(*) AS total FROM tags").fetchone()
    if not row:
        return 0
    return int(row["total"])
