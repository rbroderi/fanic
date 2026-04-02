from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import text_error
from fanic.repository import list_tag_name_suggestions

ALLOWED_TAG_TYPES = {
    "archive_warning",
    "fandom",
    "relationship",
    "character",
    "freeform",
    "category",
    "rating",
}


def _resolve_limit(value: str, *, default: int = 12, max_limit: int = 50) -> int:
    stripped = value.strip()
    if not stripped:
        return default
    if not stripped.isdigit():
        return default
    parsed = int(stripped)
    if parsed < 1:
        return 1
    if parsed > max_limit:
        return max_limit
    return parsed


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/api/tag-suggestions":
        return text_error(response, "Not found", 404)

    tag_type = request.args.get("type", "").strip()
    if tag_type not in ALLOWED_TAG_TYPES:
        return json_response(
            response,
            {"detail": "invalid tag type"},
            400,
        )

    query = request.args.get("q", "").strip()
    limit = _resolve_limit(request.args.get("limit", ""))
    suggestions = list_tag_name_suggestions(tag_type, query, limit=limit)
    return json_response(
        response,
        {
            "type": tag_type,
            "q": query,
            "limit": limit,
            "suggestions": suggestions,
        },
        200,
    )
