from html import escape

from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.repository.tags import TagPopularityRow
from fanic.repository.tags import list_top_tag_popularity
from fanic.settings import DYNAMIC_TEMPLATE_DIR

_ALLOWED_TAG_TYPES = {
    "archive_warning",
    "fandom",
    "relationship",
    "character",
    "freeform",
    "category",
    "rating",
}


def _render_fragment_template(template_name: str, replacements: dict[str, str]) -> str:
    html = (DYNAMIC_TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html


def _tag_type_options_html(selected_type: str) -> str:
    ordered_types = [
        ("archive_warning", "Archive warning"),
        ("fandom", "Fandom"),
        ("relationship", "Relationship"),
        ("character", "Character"),
        ("freeform", "Freeform"),
        ("category", "Category"),
        ("rating", "Rating"),
    ]
    options: list[str] = []
    for value, label in ordered_types:
        selected_attr = ' selected="selected"' if value == selected_type else ""
        options.append(f'<option value="{value}"{selected_attr}>{label}</option>')
    return "".join(options)


def _parse_limit(raw_limit: str, *, default: int = 50, max_limit: int = 250) -> int:
    stripped = raw_limit.strip()
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


def _normalize_tag_type(raw_type: str) -> str:
    normalized = raw_type.strip().lower()
    if normalized in _ALLOWED_TAG_TYPES:
        return normalized
    return ""


def _rows_html(rows: list[TagPopularityRow]) -> str:
    if not rows:
        return '<p class="profile-meta">No tags found for the current filters.</p>'

    rendered_rows: list[str] = []
    for row in rows:
        rendered_rows.append(
            _render_fragment_template(
                "tag-popularity-admin-row.html",
                {
                    "__TAG_POPULARITY_NAME__": escape(row["name"]),
                    "__TAG_POPULARITY_SLUG__": escape(row["slug"]),
                    "__TAG_POPULARITY_TYPE__": escape(row["type"]),
                    "__TAG_POPULARITY_ATTACHED_WORKS__": escape(str(row["attached_works"])),
                    "__TAG_POPULARITY_SEED_COUNT__": escape(str(row["seed_count"])),
                    "__TAG_POPULARITY_USAGE_COUNT__": escape(str(row["usage_count"])),
                    "__TAG_POPULARITY_EFFECTIVE__": escape(str(row["effective_popularity"])),
                },
            )
        )
    return "".join(rendered_rows)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/admin/tag-popularity":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if not is_privileged_role(role_for_user(username)):
        return text_error(response, "Forbidden", 403)

    tag_type = _normalize_tag_type(request.args.get("type", ""))
    query = request.args.get("q", "").strip()
    limit = _parse_limit(request.args.get("limit", ""))

    rows = list_top_tag_popularity(limit=limit, tag_type=tag_type, query=query)

    return render_html_template(
        request,
        response,
        "tag-popularity-admin.html",
        {
            "__TAG_POPULARITY_COUNT__": str(len(rows)),
            "__TAG_POPULARITY_QUERY__": escape(query),
            "__TAG_POPULARITY_LIMIT__": str(limit),
            "__TAG_POPULARITY_TYPE_OPTIONS__": _tag_type_options_html(tag_type),
            "__TAG_POPULARITY_ROWS_HTML__": _rows_html(rows),
        },
    )
