from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass

from fanic.repository.works import WorkPageRow


@dataclass(frozen=True, slots=True)
class PageDeletePlan:
    renumbered_pages: list[WorkPageRow]
    removed_image_name: str


def _as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def plan_delete_page(
    pages: list[WorkPageRow],
    page_index: int,
) -> PageDeletePlan:
    current_page = next(
        (page for page in pages if page["page_index"] == page_index),
        None,
    )
    if current_page is None:
        raise FileNotFoundError(f"Page index not found: {page_index}")

    image_name = _as_str(current_page["image_filename"], "")

    remaining = [page for page in pages if page["page_index"] != page_index]
    renumbered: list[WorkPageRow] = []
    for idx, page in enumerate(remaining, start=1):
        renumbered.append(
            {
                "page_index": idx,
                "image_filename": page["image_filename"],
                "thumb_filename": page["thumb_filename"],
                "width": page["width"],
                "height": page["height"],
            }
        )

    return PageDeletePlan(renumbered_pages=renumbered, removed_image_name=image_name)


def editor_delete_page_use_case(
    *,
    work_id: str,
    page_index: int,
    uploader_username: str,
    require_editor_owner: Callable[[str, str], dict[str, object]],
    list_work_page_rows: Callable[[str], list[WorkPageRow]],
    replace_work_pages: Callable[[str, list[WorkPageRow]], None],
    reconcile_chapters_after_page_changes: Callable[[str, str | None], None],
    upsert_existing_work: Callable[[dict[str, object], list[WorkPageRow]], None],
    create_work_version_snapshot: Callable[[str, str, str | None, dict[str, object]], Mapping[str, object]],
) -> dict[str, object]:
    existing_work = require_editor_owner(work_id, uploader_username)
    pages = list_work_page_rows(work_id)

    delete_plan = plan_delete_page(pages, page_index)

    replace_work_pages(work_id, delete_plan.renumbered_pages)
    reconcile_chapters_after_page_changes(work_id, delete_plan.removed_image_name)
    upsert_existing_work(existing_work, delete_plan.renumbered_pages)
    create_work_version_snapshot(
        work_id,
        "editor-delete-page",
        uploader_username,
        {"deleted_page_index": page_index},
    )

    return {
        "work_id": work_id,
        "page_count": len(delete_plan.renumbered_pages),
        "deleted_page_index": page_index,
    }
