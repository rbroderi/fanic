import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from fanic.cylinder_sites.common import MAX_PAGE_UPLOAD_BYTES
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import begin_upload_session
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import end_upload_session
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import role_for_user
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import upload_policy_error_info
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import validate_page_upload_policy
from fanic.cylinder_sites.common import validate_saved_upload_size
from fanic.ingest import editor_add_chapter
from fanic.ingest import editor_delete_chapter
from fanic.ingest import editor_delete_page
from fanic.ingest import editor_move_page
from fanic.ingest import editor_reorder_gallery
from fanic.ingest import editor_replace_page_image
from fanic.ingest import editor_update_chapter
from fanic.ingest import ingest_editor_page
from fanic.repository import add_work_comment
from fanic.repository import add_work_kudo
from fanic.repository import can_view_work
from fanic.repository import create_notification
from fanic.repository import create_work_version_snapshot
from fanic.repository import delete_work
from fanic.repository import get_work
from fanic.repository import update_work_metadata


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


def _redirect(response: ResponseLike, location: str) -> ResponseLike:
    response.status_code = 303
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = location
    response.set_data(f"See Other: {location}")
    return response


def _can_edit_work(username: str | None, uploader_username: str, *, is_admin: bool) -> bool:
    return bool(username) and (username == uploader_username or is_admin)


def _is_explicit_rating(value: object) -> bool:
    return str(value).strip().casefold() == "explicit"


def _coerce_int(value: object, default: int = 0) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [str(item) for item in items]


def _normalize_chapter_members(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    source = cast(dict[object, object], value)
    normalized: dict[str, list[str]] = {}
    for chapter_id, members in source.items():
        if not isinstance(members, list):
            continue
        normalized[str(chapter_id)] = _normalize_str_list(cast(list[object], members))
    return normalized


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["works"])
    if tail is None or len(tail) != 2:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    work_id = tail[0]
    action = tail[1]
    work = get_work(work_id)
    if not work:
        return text_error(response, "Work not found", 404)

    username = current_user(request)
    user_role = role_for_user(username)
    is_admin = user_role in {"superadmin", "admin"}

    if action == "delete":
        if not is_admin:
            return text_error(response, "Forbidden", 403)
        _ = delete_work(work_id)
        return _redirect(response, "/")

    if not can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    if action == "kudos":
        if not username:
            return _redirect(response, f"/works/{work_id}?msg=login-required")
        inserted = add_work_kudo(work_id, username)
        if inserted:
            uploader_username = str(work.get("uploader_username") if work.get("uploader_username") else "")
            if uploader_username and uploader_username != username:
                work_title = str(work.get("title", "Untitled"))
                _ = create_notification(
                    uploader_username,
                    actor_username=username,
                    work_id=work_id,
                    kind="kudo",
                    message=f'{username} left kudos on your work "{work_title}".',
                    href=f"/works/{work_id}",
                )
        return _redirect(
            response,
            f"/works/{work_id}?msg={'kudos-saved' if inserted else 'already-kudoed'}",
        )

    if action == "comments":
        if not username:
            return _redirect(response, f"/works/{work_id}?msg=login-required")

        body = request.form.get("comment_body", "").strip()
        if not body:
            return _redirect(response, f"/works/{work_id}?msg=comment-empty")

        chapter_raw = request.form.get("chapter_number", "").strip()
        chapter_number: int | None
        if chapter_raw:
            try:
                chapter_number = int(chapter_raw)
            except ValueError:
                return _redirect(response, f"/works/{work_id}?msg=chapter-invalid")
            max_chapter = _coerce_int(work.get("page_count"), 0)
            if chapter_number < 1 or chapter_number > max_chapter:
                return _redirect(response, f"/works/{work_id}?msg=chapter-invalid")
        else:
            chapter_number = None

        add_work_comment(work_id, username, body, chapter_number=chapter_number)
        uploader_username = str(work.get("uploader_username") if work.get("uploader_username") else "")
        if uploader_username and uploader_username != username:
            work_title = str(work.get("title", "Untitled"))
            chapter_text = f" on chapter {chapter_number}" if chapter_number is not None else ""
            _ = create_notification(
                uploader_username,
                actor_username=username,
                work_id=work_id,
                kind="comment",
                message=f'{username} commented{chapter_text} on your work "{work_title}".',
                href=f"/works/{work_id}",
            )
        return _redirect(response, f"/works/{work_id}?msg=comment-saved")

    if action != "edit":
        return text_error(response, "Not found", 404)

    uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
    if not _can_edit_work(username, uploader, is_admin=is_admin):
        return text_error(response, "Forbidden", 403)

    assert username is not None
    edit_action = request.form.get("edit_action", "").strip()

    if edit_action == "editor-add-page":
        raw_upload = request.files.get("page_image")
        page_upload = raw_upload if _has_selected_file(raw_upload) else None
        if page_upload is None:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-file-required")

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            error_code, _ = upload_policy_error_info(page_policy_error)
            msg = (
                "page-add-unsupported-extension"
                if error_code == "unsupported_extension"
                else (
                    "page-add-unsupported-content-type"
                    if error_code == "unsupported_content_type"
                    else "page-add-failed"
                )
            )
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")

        started_upload_session = False
        allowed, limit_code, _ = begin_upload_session(username)
        if not allowed:
            msg = "page-add-rate-limited" if limit_code == "upload_rate_limited" else "page-add-busy"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")

        editor_metadata: dict[str, object] = {
            "title": str(work.get("title", "Untitled")),
            "summary": str(work.get("summary", "")),
            "rating": str(work.get("rating", "Not Rated")),
            "status": str(work.get("status", "in_progress")),
            "language": str(work.get("language", "en")),
        }

        try:
            started_upload_session = True
            insert_after_page_index: int | None = None
            insert_after_raw = request.form.get("insert_after_page_index", "").strip()
            if insert_after_raw:
                parsed = int(insert_after_raw)
                if parsed > 0:
                    insert_after_page_index = parsed

            with TemporaryDirectory() as temp_dir:
                page_path = Path(temp_dir) / Path(page_upload.filename if page_upload.filename else "page.png").name
                page_upload.save(page_path)
                page_size_error = validate_saved_upload_size(
                    page_path,
                    MAX_PAGE_UPLOAD_BYTES,
                    "Page upload",
                )
                if page_size_error:
                    return _redirect(response, f"/works/{work_id}/edit?msg=page-add-too-large")
                result = ingest_editor_page(
                    image_path=page_path,
                    metadata=editor_metadata,
                    uploader_username=username,
                    work_id=work_id,
                    insert_after_page_index=insert_after_page_index,
                )
            msg = "page-added-rating-elevated" if bool(result.get("rating_auto_elevated")) else "page-added"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")
        except ValueError as exc:
            if "Blocked image" in str(exc):
                return _redirect(response, f"/works/{work_id}/edit?msg=page-blocked")
            return _redirect(response, f"/works/{work_id}/edit?msg=page-add-failed")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-add-failed")
        finally:
            if started_upload_session:
                end_upload_session(username)

    if edit_action == "editor-replace-page":
        raw_upload = request.files.get("page_image")
        page_upload = raw_upload if _has_selected_file(raw_upload) else None
        if page_upload is None:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-file-required")

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            error_code, _ = upload_policy_error_info(page_policy_error)
            msg = (
                "page-replace-unsupported-extension"
                if error_code == "unsupported_extension"
                else (
                    "page-replace-unsupported-content-type"
                    if error_code == "unsupported_content_type"
                    else "page-replace-failed"
                )
            )
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")
        started_upload_session = False
        allowed, limit_code, _ = begin_upload_session(username)
        if not allowed:
            msg = "page-replace-rate-limited" if limit_code == "upload_rate_limited" else "page-replace-busy"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")

        try:
            started_upload_session = True
            page_index = int(request.form.get("page_index", "0"))
            with TemporaryDirectory() as temp_dir:
                page_path = Path(temp_dir) / Path(page_upload.filename if page_upload.filename else "page.png").name
                page_upload.save(page_path)
                page_size_error = validate_saved_upload_size(
                    page_path,
                    MAX_PAGE_UPLOAD_BYTES,
                    "Page upload",
                )
                if page_size_error:
                    return _redirect(
                        response,
                        f"/works/{work_id}/edit?msg=page-replace-too-large",
                    )
                result = editor_replace_page_image(
                    image_path=page_path,
                    work_id=work_id,
                    page_index=page_index,
                    uploader_username=username,
                )
            msg = "page-replaced-rating-elevated" if bool(result.get("rating_auto_elevated")) else "page-replaced"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")
        except ValueError as exc:
            if "Blocked image" in str(exc):
                return _redirect(response, f"/works/{work_id}/edit?msg=page-blocked")
            return _redirect(response, f"/works/{work_id}/edit?msg=page-replace-failed")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-replace-failed")
        finally:
            if started_upload_session:
                end_upload_session(username)

    if edit_action == "editor-delete-page":
        try:
            page_index = int(request.form.get("page_index", "0"))
            _ = editor_delete_page(
                work_id=work_id,
                page_index=page_index,
                uploader_username=username,
            )
            return _redirect(response, f"/works/{work_id}/edit?msg=page-deleted")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-delete-failed")

    if edit_action == "editor-move-page":
        try:
            from_index = int(request.form.get("from_index", "0"))
            to_index = int(request.form.get("to_index", "0"))
            _ = editor_move_page(
                work_id=work_id,
                from_index=from_index,
                to_index=to_index,
                uploader_username=username,
            )
            return _redirect(response, f"/works/{work_id}/edit?msg=page-moved")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-move-failed")

    if edit_action == "editor-reorder-gallery":
        try:
            ordered_filenames_raw = request.form.get("ordered_filenames_json", "")
            chapter_members_raw = request.form.get("chapter_members_json", "{}")

            ordered_filenames_obj = json.loads(ordered_filenames_raw)
            chapter_members_obj = json.loads(chapter_members_raw)

            ordered_filenames = _normalize_str_list(ordered_filenames_obj)
            if not ordered_filenames and ordered_filenames_obj != []:
                raise ValueError("Invalid ordered_filenames_json")
            chapter_members = _normalize_chapter_members(chapter_members_obj)
            if not chapter_members and chapter_members_obj != {}:
                raise ValueError("Invalid chapter_members_json")

            _ = editor_reorder_gallery(
                work_id=work_id,
                ordered_filenames=ordered_filenames,
                chapter_members=chapter_members,
                uploader_username=username,
            )
            return _redirect(response, f"/works/{work_id}/edit?msg=page-reordered")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=page-reorder-failed")

    if edit_action == "editor-add-chapter":
        try:
            title = (
                request.form.get("chapter_title", "").strip()
                if request.form.get("chapter_title", "").strip()
                else "Untitled Chapter"
            )
            start_page = int(request.form.get("chapter_start_page", "0"))
            end_page = int(request.form.get("chapter_end_page", "0"))
            _ = editor_add_chapter(
                work_id=work_id,
                title=title,
                start_page=start_page,
                end_page=end_page,
                uploader_username=username,
            )
            return _redirect(response, f"/works/{work_id}/edit?msg=chapter-added")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=chapter-add-failed")

    if edit_action == "editor-update-chapter":
        try:
            chapter_id = int(request.form.get("chapter_id", "0"))
            title = (
                request.form.get("chapter_title", "").strip()
                if request.form.get("chapter_title", "").strip()
                else "Untitled Chapter"
            )
            start_page = int(request.form.get("chapter_start_page", "0"))
            end_page = int(request.form.get("chapter_end_page", "0"))
            updated = editor_update_chapter(
                work_id=work_id,
                chapter_id=chapter_id,
                title=title,
                start_page=start_page,
                end_page=end_page,
                uploader_username=username,
            )
            msg = "chapter-updated" if updated else "chapter-update-failed"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=chapter-update-failed")

    if edit_action == "editor-delete-chapter":
        try:
            chapter_id = int(request.form.get("chapter_id", "0"))
            deleted = editor_delete_chapter(
                work_id=work_id,
                chapter_id=chapter_id,
                uploader_username=username,
            )
            msg = "chapter-deleted" if deleted else "chapter-delete-failed"
            return _redirect(response, f"/works/{work_id}/edit?msg={msg}")
        except Exception:
            return _redirect(response, f"/works/{work_id}/edit?msg=chapter-delete-failed")

    series_index_raw = request.form.get("series_index", "").strip()
    try:
        series_index = int(series_index_raw) if series_index_raw else None
    except ValueError:
        series_index = None

    status = request.form.get("status", "").strip()
    if status not in {"in_progress", "complete"}:
        status = "in_progress"

    metadata: dict[str, object] = {
        "title": request.form.get("title", "").strip()
        if request.form.get("title", "").strip()
        else str(work.get("title", "Untitled")),
        "summary": request.form.get("summary", "").strip(),
        "rating": (request.form.get("rating", "").strip() if request.form.get("rating", "").strip() else "Not Rated"),
        "warnings": _csv(request.form.get("warnings", "")),
        "status": status,
        "language": (request.form.get("language", "").strip() if request.form.get("language", "").strip() else "en"),
        "series": request.form.get("series", "").strip(),
        "series_index": series_index,
        "published_at": request.form.get("published_at", "").strip(),
        "fandoms": _csv(request.form.get("fandoms", "")),
        "relationships": _csv(request.form.get("relationships", "")),
        "characters": _csv(request.form.get("characters", "")),
        "freeform_tags": _csv(request.form.get("freeform_tags", "")),
    }

    current_rating = work.get("rating", "Not Rated")
    requested_rating = metadata.get("rating", "Not Rated")
    if not is_admin and _is_explicit_rating(current_rating) and not _is_explicit_rating(requested_rating):
        return _redirect(response, f"/works/{work_id}/edit?msg=explicit-rating-locked")

    update_work_metadata(
        work_id,
        metadata,
        editor_username=username,
        edited_by_admin=is_admin,
    )
    _ = create_work_version_snapshot(
        work_id,
        action="metadata-edit",
        actor=username,
        details={"edited_by_admin": is_admin},
    )
    return _redirect(response, f"/works/{work_id}/edit?msg=saved")
