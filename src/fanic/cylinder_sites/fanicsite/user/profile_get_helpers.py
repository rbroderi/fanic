from collections.abc import Mapping
from collections.abc import Sequence
from html import escape


def recent_history_html(history_rows: Sequence[Mapping[str, object]]) -> str:
    if not history_rows:
        return '<p class="profile-meta">No reading history yet.</p>'

    items: list[str] = []
    for row in history_rows:
        work_id = escape(str(row.get("work_id", "")))
        work_title = escape(str(row.get("work_title", "Untitled")))
        page_index = escape(str(row.get("page_index", 1)))
        updated_at = escape(str(row.get("updated_at", "")))
        items.append(
            f'<li><a href="/tools/reader/{work_id}">{work_title}</a> '
            f'<span class="profile-meta">(continue at page {page_index}; last viewed {updated_at})</span></li>'
        )
    return '<ul class="work-links">' + "".join(items) + "</ul>"
