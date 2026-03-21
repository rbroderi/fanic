from __future__ import annotations

from pathlib import Path

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    json_response,
    page_file_for,
    route_tail,
    send_file,
    thumb_file_for,
)
from fanic.repository import (
    can_view_work,
    get_manifest,
    get_page_files,
    get_work,
    list_works,
    load_progress,
)


def _can_view_work(request: RequestLike, work: dict[str, object]) -> bool:
    return can_view_work(current_user(request), work)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "works"])
    if tail is None:
        return json_response(response, {"detail": "Not found"}, 404)

    if tail == []:
        filters = {
            "q": request.args.get("q", ""),
            "fandom": request.args.get("fandom", ""),
            "tag": request.args.get("tag", ""),
            "rating": request.args.get("rating", ""),
            "status": request.args.get("status", ""),
        }
        works = [work for work in list_works(filters) if _can_view_work(request, work)]
        return json_response(response, {"works": works})

    work_id = tail[0]

    if len(tail) == 1:
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"work": work})

    if len(tail) == 2 and tail[1] == "manifest":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)
        manifest = get_manifest(work_id)
        if not manifest:
            return json_response(response, {"detail": "Work not found"}, 404)
        return json_response(response, {"manifest": manifest})

    if len(tail) == 2 and tail[1] == "download":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)

        cbz_path = work.get("cbz_path")
        if not isinstance(cbz_path, str):
            return json_response(response, {"detail": "Invalid archive path"}, 500)

        slug = work.get("slug")
        filename = f"{slug}.cbz" if isinstance(slug, str) else f"{work_id}.cbz"
        return send_file(response, Path(cbz_path), filename)

    if len(tail) == 4 and tail[1] == "pages":
        work = get_work(work_id)
        if not work:
            return json_response(response, {"detail": "Work not found"}, 404)
        if not _can_view_work(request, work):
            return json_response(response, {"detail": "Work not found"}, 404)

        try:
            page_index = int(tail[2])
        except ValueError:
            return json_response(response, {"detail": "Page not found"}, 404)

        page = get_page_files(work_id, page_index)
        if not page:
            return json_response(response, {"detail": "Page not found"}, 404)

        if tail[3] == "image":
            image_name = page.get("image")
            if not image_name:
                return json_response(response, {"detail": "Page image missing"}, 404)
            return send_file(response, page_file_for(work_id, image_name))

        if tail[3] == "thumb":
            thumb_name = page.get("thumb")
            if not thumb_name:
                return json_response(response, {"detail": "Page thumb not found"}, 404)
            return send_file(response, thumb_file_for(work_id, thumb_name))

    if len(tail) == 2 and tail[1] == "progress":
        user_id = request.args.get("user_id", "anon")
        return json_response(response, {"page_index": load_progress(work_id, user_id)})

    return json_response(response, {"detail": "Not found"}, 404)
