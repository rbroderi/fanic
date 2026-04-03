import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from fanic.authorization import AuthorizationContext
from fanic.authorization import ComicPolicy
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.rate_limit import begin_upload_session
from fanic.cylinder_sites.common.rate_limit import end_upload_session
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.cylinder_sites.common.security import MAX_PAGE_UPLOAD_BYTES
from fanic.cylinder_sites.common.security import enforce_https_termination
from fanic.cylinder_sites.common.security import route_tail
from fanic.cylinder_sites.common.security import upload_policy_error_info
from fanic.cylinder_sites.common.security import validate_csrf
from fanic.cylinder_sites.common.security import validate_page_upload_policy
from fanic.cylinder_sites.common.security import validate_saved_upload_size
from fanic.cylinder_sites.common.session import current_user
from fanic.cylinder_sites.common.session import role_for_user
from fanic.cylinder_sites.fanicsite.comic_post_service import build_metadata_from_form
from fanic.cylinder_sites.fanicsite.comic_post_service import (
    should_lock_explicit_demotion,
)
from fanic.cylinder_sites.user_roles import is_privileged_role
from fanic.ingest import editor_add_chapter
from fanic.ingest import editor_delete_chapter
from fanic.ingest import editor_delete_page
from fanic.ingest import editor_move_page
from fanic.ingest import editor_reorder_gallery
from fanic.ingest import editor_replace_page_image
from fanic.ingest import editor_update_chapter
from fanic.ingest import ingest_editor_page
from fanic.repository.users import create_notification
from fanic.repository.works import add_work_comment
from fanic.repository.works import add_work_kudo
from fanic.repository.works import can_view_work
from fanic.repository.works import create_work_version_snapshot
from fanic.repository.works import delete_work
from fanic.repository.works import get_work
from fanic.repository.works import update_work_metadata


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


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
    tail = route_tail(request, ["comic"])
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
    is_admin = is_privileged_role(user_role)
    uploader = str(work.get("uploader_username") if work.get("uploader_username") else "")
    normalized_username = str(username if username else "")

    if action == "delete":
        delete_ctx = AuthorizationContext.from_inputs(
            current_username=normalized_username,
            current_role=user_role,
            owner_username=uploader,
        )
        if not ComicPolicy.can_delete(delete_ctx):
            return text_error(response, "Forbidden", 403)
        _ = delete_work(work_id)
        return _redirect(response, "/")

    if not can_view_work(username, work):
        return text_error(response, "Work not found", 404)

    if action == "kudos":
        if not username:
            return _redirect(response, f"/comic/{work_id}?msg=login-required")
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
                    href=f"/comic/{work_id}",
                )
        return _redirect(
            response,
            f"/comic/{work_id}?msg={'kudos-saved' if inserted else 'already-kudoed'}",
        )

    if action == "comments":
        if not username:
            return _redirect(response, f"/comic/{work_id}?msg=login-required")

        body = request.form.get("comment_body", "").strip()
        if not body:
            return _redirect(response, f"/comic/{work_id}?msg=comment-empty")

        chapter_raw = request.form.get("chapter_number", "").strip()
        chapter_number: int | None
        if chapter_raw:
            try:
                chapter_number = int(chapter_raw)
            except ValueError:
                return _redirect(response, f"/comic/{work_id}?msg=chapter-invalid")
            max_chapter = _coerce_int(work.get("page_count"), 0)
            if chapter_number < 1 or chapter_number > max_chapter:
                return _redirect(response, f"/comic/{work_id}?msg=chapter-invalid")
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
                href=f"/comic/{work_id}",
            )
        return _redirect(response, f"/comic/{work_id}?msg=comment-saved")

    if action != "edit":
        return text_error(response, "Not found", 404)

    edit_ctx = AuthorizationContext.from_inputs(
        current_username=normalized_username,
        current_role=user_role,
        owner_username=uploader,
    )
    if not ComicPolicy.can_edit(edit_ctx):
        return text_error(response, "Forbidden", 403)

    assert username is not None
    edit_action = request.form.get("edit_action", "").strip()

    if edit_action == "editor-add-page":
        raw_upload = request.files.get("page_image")
        page_upload = raw_upload if _has_selected_file(raw_upload) else None
        if page_upload is None:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-file-required")

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            policy_error_info = upload_policy_error_info(page_policy_error)
            error_code = policy_error_info.error_code
            msg = (
                "page-add-unsupported-extension"
                if error_code == "unsupported_extension"
                else (
                    "page-add-unsupported-content-type"
                    if error_code == "unsupported_content_type"
                    else "page-add-failed"
                )
            )
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")

        started_upload_session = False
        upload_session = begin_upload_session(username)
        if not upload_session.allowed:
            msg = "page-add-rate-limited" if upload_session.limit_code == "upload_rate_limited" else "page-add-busy"
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")

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
                    return _redirect(response, f"/comic/{work_id}/edit?msg=page-add-too-large")
                result = ingest_editor_page(
                    image_path=page_path,
                    metadata=editor_metadata,
                    uploader_username=username,
                    work_id=work_id,
                    insert_after_page_index=insert_after_page_index,
                )
            msg = "page-added-rating-elevated" if bool(result.get("rating_auto_elevated")) else "page-added"
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")
        except ValueError as exc:
            if "Blocked image" in str(exc):
                return _redirect(response, f"/comic/{work_id}/edit?msg=page-blocked")
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-add-failed")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-add-failed")
        finally:
            if started_upload_session:
                end_upload_session(username)

    if edit_action == "editor-replace-page":
        raw_upload = request.files.get("page_image")
        page_upload = raw_upload if _has_selected_file(raw_upload) else None
        if page_upload is None:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-file-required")

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            policy_error_info = upload_policy_error_info(page_policy_error)
            error_code = policy_error_info.error_code
            msg = (
                "page-replace-unsupported-extension"
                if error_code == "unsupported_extension"
                else (
                    "page-replace-unsupported-content-type"
                    if error_code == "unsupported_content_type"
                    else "page-replace-failed"
                )
            )
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")
        started_upload_session = False
        upload_session = begin_upload_session(username)
        if not upload_session.allowed:
            msg = (
                "page-replace-rate-limited"
                if upload_session.limit_code == "upload_rate_limited"
                else "page-replace-busy"
            )
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")

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
                        f"/comic/{work_id}/edit?msg=page-replace-too-large",
                    )
                result = editor_replace_page_image(
                    image_path=page_path,
                    work_id=work_id,
                    page_index=page_index,
                    uploader_username=username,
                )
            msg = "page-replaced-rating-elevated" if bool(result.get("rating_auto_elevated")) else "page-replaced"
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")
        except ValueError as exc:
            if "Blocked image" in str(exc):
                return _redirect(response, f"/comic/{work_id}/edit?msg=page-blocked")
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-replace-failed")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-replace-failed")
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
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-deleted")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-delete-failed")

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
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-moved")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-move-failed")

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
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-reordered")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=page-reorder-failed")

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
            return _redirect(response, f"/comic/{work_id}/edit?msg=chapter-added")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=chapter-add-failed")

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
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=chapter-update-failed")

    if edit_action == "editor-delete-chapter":
        try:
            chapter_id = int(request.form.get("chapter_id", "0"))
            deleted = editor_delete_chapter(
                work_id=work_id,
                chapter_id=chapter_id,
                uploader_username=username,
            )
            msg = "chapter-deleted" if deleted else "chapter-delete-failed"
            return _redirect(response, f"/comic/{work_id}/edit?msg={msg}")
        except Exception:
            return _redirect(response, f"/comic/{work_id}/edit?msg=chapter-delete-failed")

    metadata = build_metadata_from_form(
        existing_title=work.get("title", "Untitled"),
        title_raw=request.form.get("title", ""),
        summary_raw=request.form.get("summary", ""),
        rating_raw=request.form.get("rating", ""),
        warnings_raw=request.form.get("warnings", ""),
        status_raw=request.form.get("status", ""),
        language_raw=request.form.get("language", ""),
        series_raw=request.form.get("series", ""),
        series_index_raw=request.form.get("series_index", ""),
        published_at_raw=request.form.get("published_at", ""),
        fandoms_raw=request.form.get("fandoms", ""),
        relationships_raw=request.form.get("relationships", ""),
        characters_raw=request.form.get("characters", ""),
        freeform_tags_raw=request.form.get("freeform_tags", ""),
    )

    current_rating = work.get("rating", "Not Rated")
    requested_rating = metadata.get("rating", "Not Rated")
    if should_lock_explicit_demotion(
        is_admin=is_admin,
        current_rating=current_rating,
        requested_rating=requested_rating,
    ):
        return _redirect(response, f"/comic/{work_id}/edit?msg=explicit-rating-locked")

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
    return _redirect(response, f"/comic/{work_id}/edit?msg=saved")
