from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    text_error,
)
from fanic.cylinder_sites.ingest_page import render_ingest_page
from fanic.ingest import (
    ModerationBlockedError,
    editor_add_chapter,
    editor_delete_chapter,
    editor_delete_page,
    editor_move_page,
    editor_reorder_gallery,
    editor_replace_page_image,
    editor_update_chapter,
    ingest_cbz,
    ingest_editor_page,
)
from fanic.ingest_progress import set_progress
from fanic.moderation import get_explicit_threshold
from fanic.repository import get_work, list_work_chapters, list_work_page_rows


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


def _collect_metadata_from_form(request: RequestLike) -> dict[str, object]:
    metadata: dict[str, object] = {
        "title": request.form.get("title", "").strip(),
        "summary": request.form.get("summary", "").strip(),
        "rating": request.form.get("rating", "").strip(),
        "warnings": _csv(request.form.get("warnings", "")),
        "status": request.form.get("status", "").strip() or "in_progress",
        "language": request.form.get("language", "").strip() or "en",
        "series": request.form.get("series", "").strip(),
        "series_index": request.form.get("series_index", "").strip(),
        "published_at": request.form.get("published_at", "").strip(),
        "fandoms": _csv(request.form.get("fandoms", "")),
        "relationships": _csv(request.form.get("relationships", "")),
        "characters": _csv(request.form.get("characters", "")),
        "freeform_tags": _csv(request.form.get("freeform_tags", "")),
    }

    clean: dict[str, object] = {}
    for key, value in metadata.items():
        if isinstance(value, str) and value:
            clean[key] = value
        elif isinstance(value, list) and value:
            clean[key] = value
    return clean


def _editor_state_from_form(request: RequestLike) -> dict[str, str]:
    editor_work_id = request.form.get("editor_work_id", "").strip()
    editor_title = request.form.get("editor_title", "").strip()
    editor_summary = request.form.get("editor_summary", "").strip()
    editor_rating = request.form.get("editor_rating", "").strip() or "Not Rated"
    editor_status = request.form.get("editor_status", "").strip() or "in_progress"
    editor_language = request.form.get("editor_language", "").strip() or "en"

    if editor_work_id and (not editor_title or not editor_summary):
        work = get_work(editor_work_id)
        if work:
            if not editor_title:
                editor_title = str(work.get("title", ""))
            if not editor_summary:
                editor_summary = str(work.get("summary", ""))
            if not request.form.get("editor_rating", "").strip():
                editor_rating = str(work.get("rating", "Not Rated"))
            if not request.form.get("editor_status", "").strip():
                editor_status = str(work.get("status", "in_progress"))
            if not request.form.get("editor_language", "").strip():
                editor_language = str(work.get("language", "en"))

    return {
        "editor_work_id": editor_work_id,
        "editor_title": editor_title,
        "editor_summary": editor_summary,
        "editor_rating": editor_rating,
        "editor_status": editor_status,
        "editor_language": editor_language,
    }


def _render_editor_result(
    request: RequestLike,
    response: ResponseLike,
    editor_state: dict[str, str],
    *,
    ingest_status: str,
    ingest_status_kind: str,
    result_payload: dict[str, object] | None = None,
) -> ResponseLike:
    work_id = editor_state.get("editor_work_id", "")
    pages = list_work_page_rows(work_id) if work_id else []
    chapters = list_work_chapters(work_id) if work_id else []
    return render_ingest_page(
        request,
        response,
        editor_work_id=work_id,
        editor_title=editor_state.get("editor_title", ""),
        editor_summary=editor_state.get("editor_summary", ""),
        editor_rating=editor_state.get("editor_rating", "Not Rated"),
        editor_status=editor_state.get("editor_status", "in_progress"),
        editor_language=editor_state.get("editor_language", "en"),
        editor_pages=pages,
        editor_chapters=chapters,
        ingest_status=ingest_status,
        ingest_status_kind=ingest_status_kind,
        result_payload=result_payload,
    )


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/ingest":
        return text_error(response, "Not found", 404)

    username = current_user(request)
    if username is None:
        return render_ingest_page(
            request,
            response,
            ingest_status="Login required before uploads.",
            ingest_status_kind="error",
        )

    action = request.form.get("action", "").strip()
    terms_accepted = request.form.get("agree_terms", "").strip().lower() in {
        "on",
        "true",
        "1",
        "yes",
    }
    raw_cbz_upload = request.files.get("cbz")
    cbz_upload = raw_cbz_upload if _has_selected_file(raw_cbz_upload) else None
    raw_page_upload = request.files.get("page_image")
    page_upload = raw_page_upload if _has_selected_file(raw_page_upload) else None
    upload_token = request.form.get("upload_token", "").strip()

    if action in {"load-metadata", "ingest"}:
        if not terms_accepted:
            return render_ingest_page(
                request,
                response,
                ingest_status="You must agree to the Terms and Conditions before uploading.",
                ingest_status_kind="error",
            )

        if cbz_upload is None:
            return render_ingest_page(
                request,
                response,
                ingest_status="Please choose a CBZ file first.",
                ingest_status_kind="error",
            )

        try:
            if upload_token:
                set_progress(
                    upload_token,
                    stage="starting",
                    message="Starting import",
                )

            metadata = _collect_metadata_from_form(request)
            override_path: Path | None = None
            with TemporaryDirectory() as temp_dir:
                cbz_path = (
                    Path(temp_dir) / Path(cbz_upload.filename or "upload.cbz").name
                )
                cbz_upload.save(cbz_path)
                if metadata:
                    override_path = Path(temp_dir) / "metadata.json"
                    _ = override_path.write_text(
                        json.dumps(metadata, ensure_ascii=True),
                        encoding="utf-8",
                    )

                result = ingest_cbz(
                    cbz_path,
                    metadata_override_path=override_path,
                    uploader_username=username,
                    progress_hook=(
                        (
                            lambda stage, message, current, total: set_progress(
                                upload_token,
                                stage=stage,
                                message=message,
                                current=current,
                                total=total,
                                done=False,
                                ok=False,
                            )
                        )
                        if upload_token
                        else None
                    ),
                )

            if upload_token:
                set_progress(
                    upload_token,
                    stage="done",
                    message="Import complete",
                    done=True,
                    ok=True,
                )

            work_id = str(result.get("work_id", ""))
            work = get_work(work_id) or {}
            editor_state = {
                "editor_work_id": work_id,
                "editor_title": str(work.get("title", "") or ""),
                "editor_summary": str(work.get("summary", "") or ""),
                "editor_rating": str(work.get("rating", "Not Rated") or "Not Rated"),
                "editor_status": str(
                    work.get("status", "in_progress") or "in_progress"
                ),
                "editor_language": str(work.get("language", "en") or "en"),
            }

            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="CBZ imported into editor draft. Review pages, reorder, and finalize using the editor workflow.",
                ingest_status_kind="success",
                result_payload={
                    "ok": True,
                    "mode": "editor",
                    "uploaded_by": username,
                    "result": result,
                },
            )
        except ModerationBlockedError as exc:
            if upload_token:
                set_progress(
                    upload_token,
                    stage="blocked",
                    message="Blocked by moderation policy",
                    done=True,
                    ok=False,
                )
            moderation = exc.moderation
            reasons_obj = moderation.get("reasons")
            reasons: list[str] = []
            if isinstance(reasons_obj, list):
                reasons = [str(reason) for reason in reasons_obj]

            source_member = str(moderation.get("source_member", "") or "")
            source_suffix = f" ({source_member})" if source_member else ""
            return render_ingest_page(
                request,
                response,
                ingest_status=(
                    f"CBZ import blocked by moderation policy{source_suffix}."
                ),
                ingest_status_kind="error",
                result_payload={
                    "ok": False,
                    "mode": "editor",
                    "blocked": True,
                    "explicit_threshold": get_explicit_threshold(),
                    "error": "moderation_blocked",
                    "message": str(exc),
                    "moderation": {
                        "allow": bool(moderation.get("allow", False)),
                        "style": str(moderation.get("style", "unknown")),
                        "style_debug": moderation.get("style_debug", {}),
                        "style_confidences": moderation.get("style_confidences", {}),
                        "nsfw_score": float(moderation.get("nsfw_score", 0.0) or 0.0),
                        "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                        "reasons": reasons,
                        "source_member": source_member,
                    },
                },
            )
        except Exception as exc:
            if upload_token:
                set_progress(
                    upload_token,
                    stage="failed",
                    message=f"Import failed: {exc}",
                    done=True,
                    ok=False,
                )
            return render_ingest_page(
                request,
                response,
                ingest_status=f"CBZ import failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-add-page":
        editor_state = _editor_state_from_form(request)

        is_new_editor_draft = not editor_state.get("editor_work_id", "").strip()
        if is_new_editor_draft and not terms_accepted:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="You must agree to the Terms and Conditions before uploading.",
                ingest_status_kind="error",
            )

        if page_upload is None:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Choose an image page before uploading.",
                ingest_status_kind="error",
            )

        editor_metadata: dict[str, object] = {
            "title": editor_state["editor_title"],
            "summary": editor_state["editor_summary"],
            "rating": editor_state["editor_rating"],
            "status": editor_state["editor_status"],
            "language": editor_state["editor_language"],
        }

        try:
            with TemporaryDirectory() as temp_dir:
                page_path = (
                    Path(temp_dir) / Path(page_upload.filename or "page.png").name
                )
                page_upload.save(page_path)
                result = ingest_editor_page(
                    image_path=page_path,
                    metadata=editor_metadata,
                    uploader_username=username,
                    work_id=editor_state["editor_work_id"] or None,
                )

            work_id = str(result.get("work_id", ""))
            editor_state["editor_work_id"] = work_id
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=(
                    "Page uploaded to comic draft."
                    if not bool(result.get("rating_auto_elevated"))
                    else (
                        "Page uploaded to comic draft. Rating auto-updated from "
                        f"{result.get('rating_before')} to {result.get('rating_after')} based on moderation."
                    )
                ),
                ingest_status_kind="success",
                result_payload={
                    "ok": True,
                    "mode": "editor",
                    "uploaded_by": username,
                    "result": result,
                },
            )
        except ModerationBlockedError as exc:
            moderation = exc.moderation
            reasons_obj = moderation.get("reasons")
            reasons: list[str] = []
            if isinstance(reasons_obj, list):
                reasons = [str(reason) for reason in reasons_obj]

            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Editor upload blocked by moderation policy.",
                ingest_status_kind="error",
                result_payload={
                    "ok": False,
                    "mode": "editor",
                    "blocked": True,
                    "explicit_threshold": get_explicit_threshold(),
                    "error": "moderation_blocked",
                    "message": str(exc),
                    "moderation": {
                        "allow": bool(moderation.get("allow", False)),
                        "style": str(moderation.get("style", "unknown")),
                        "style_debug": moderation.get("style_debug", {}),
                        "style_confidences": moderation.get("style_confidences", {}),
                        "nsfw_score": float(moderation.get("nsfw_score", 0.0) or 0.0),
                        "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                        "reasons": reasons,
                    },
                },
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Editor upload failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-replace-page":
        editor_state = _editor_state_from_form(request)
        if page_upload is None:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Choose an image to replace the page.",
                ingest_status_kind="error",
            )

        try:
            page_index = int(request.form.get("page_index", "0"))
            with TemporaryDirectory() as temp_dir:
                page_path = (
                    Path(temp_dir) / Path(page_upload.filename or "page.png").name
                )
                page_upload.save(page_path)
                result = editor_replace_page_image(
                    image_path=page_path,
                    work_id=editor_state["editor_work_id"],
                    page_index=page_index,
                    uploader_username=username,
                )
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=(
                    "Page replaced."
                    if not bool(result.get("rating_auto_elevated"))
                    else (
                        "Page replaced. Rating auto-updated from "
                        f"{result.get('rating_before')} to {result.get('rating_after')} based on moderation."
                    )
                ),
                ingest_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except ModerationBlockedError as exc:
            moderation = exc.moderation
            reasons_obj = moderation.get("reasons")
            reasons: list[str] = []
            if isinstance(reasons_obj, list):
                reasons = [str(reason) for reason in reasons_obj]

            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Replace blocked by moderation policy.",
                ingest_status_kind="error",
                result_payload={
                    "ok": False,
                    "mode": "editor",
                    "blocked": True,
                    "explicit_threshold": get_explicit_threshold(),
                    "error": "moderation_blocked",
                    "message": str(exc),
                    "moderation": {
                        "allow": bool(moderation.get("allow", False)),
                        "style": str(moderation.get("style", "unknown")),
                        "style_debug": moderation.get("style_debug", {}),
                        "style_confidences": moderation.get("style_confidences", {}),
                        "nsfw_score": float(moderation.get("nsfw_score", 0.0) or 0.0),
                        "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                        "reasons": reasons,
                    },
                },
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Replace failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-delete-page":
        editor_state = _editor_state_from_form(request)
        try:
            page_index = int(request.form.get("page_index", "0"))
            result = editor_delete_page(
                work_id=editor_state["editor_work_id"],
                page_index=page_index,
                uploader_username=username,
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Page deleted.",
                ingest_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Delete failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-move-page":
        editor_state = _editor_state_from_form(request)
        try:
            from_index = int(request.form.get("from_index", "0"))
            to_index = int(request.form.get("to_index", "0"))
            result = editor_move_page(
                work_id=editor_state["editor_work_id"],
                from_index=from_index,
                to_index=to_index,
                uploader_username=username,
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Page reordered.",
                ingest_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Reorder failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-reorder-gallery":
        editor_state = _editor_state_from_form(request)
        try:
            ordered_filenames_raw = request.form.get("ordered_filenames_json", "")
            chapter_members_raw = request.form.get("chapter_members_json", "{}")

            ordered_filenames = json.loads(ordered_filenames_raw)
            chapter_members = json.loads(chapter_members_raw)
            if not isinstance(ordered_filenames, list):
                raise ValueError("Invalid ordered_filenames_json")
            if not isinstance(chapter_members, dict):
                raise ValueError("Invalid chapter_members_json")

            result = editor_reorder_gallery(
                work_id=editor_state["editor_work_id"],
                ordered_filenames=[str(name) for name in ordered_filenames],
                chapter_members={
                    str(chapter_id): [str(name) for name in members]
                    for chapter_id, members in chapter_members.items()
                    if isinstance(members, list)
                },
                uploader_username=username,
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Gallery order saved. Page order and chapter assignments updated.",
                ingest_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Reorder failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-add-chapter":
        editor_state = _editor_state_from_form(request)
        try:
            title = request.form.get("chapter_title", "").strip() or "Untitled Chapter"
            start_page = int(request.form.get("chapter_start_page", "0"))
            end_page = int(request.form.get("chapter_end_page", "0"))
            result = editor_add_chapter(
                work_id=editor_state["editor_work_id"],
                title=title,
                start_page=start_page,
                end_page=end_page,
                uploader_username=username,
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Chapter added.",
                ingest_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Add chapter failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-delete-chapter":
        editor_state = _editor_state_from_form(request)
        try:
            chapter_id = int(request.form.get("chapter_id", "0"))
            deleted = editor_delete_chapter(
                work_id=editor_state["editor_work_id"],
                chapter_id=chapter_id,
                uploader_username=username,
            )
            if not deleted:
                raise ValueError("Chapter not found")
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Chapter deleted.",
                ingest_status_kind="success",
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Delete chapter failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-update-chapter":
        editor_state = _editor_state_from_form(request)
        try:
            chapter_id = int(request.form.get("chapter_id", "0"))
            title = request.form.get("chapter_title", "").strip() or "Untitled Chapter"
            start_page = int(request.form.get("chapter_start_page", "0"))
            end_page = int(request.form.get("chapter_end_page", "0"))
            updated = editor_update_chapter(
                work_id=editor_state["editor_work_id"],
                chapter_id=chapter_id,
                title=title,
                start_page=start_page,
                end_page=end_page,
                uploader_username=username,
            )
            if not updated:
                raise ValueError("Chapter not found")
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status="Chapter updated.",
                ingest_status_kind="success",
            )
        except Exception as exc:
            return _render_editor_result(
                request,
                response,
                editor_state,
                ingest_status=f"Update chapter failed: {exc}",
                ingest_status_kind="error",
            )

    return render_ingest_page(request, response)
