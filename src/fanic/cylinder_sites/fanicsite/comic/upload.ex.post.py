import json
import shutil
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from tempfile import mkdtemp

from fanic.cylinder_sites.common import MAX_CBZ_UPLOAD_BYTES
from fanic.cylinder_sites.common import MAX_PAGE_UPLOAD_BYTES
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import admin_aware_detail
from fanic.cylinder_sites.common import begin_comic_ingest_session
from fanic.cylinder_sites.common import begin_upload_session
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import end_comic_ingest_session
from fanic.cylinder_sites.common import end_upload_session
from fanic.cylinder_sites.common import enforce_https_termination
from fanic.cylinder_sites.common import log_exception
from fanic.cylinder_sites.common import request_id
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.common import validate_cbz_upload_policy
from fanic.cylinder_sites.common import validate_csrf
from fanic.cylinder_sites.common import validate_page_upload_policy
from fanic.cylinder_sites.common import validate_saved_upload_size
from fanic.cylinder_sites.fanicsite.comic.upload_page import render_upload_page
from fanic.ingest import ModerationBlockedError
from fanic.ingest import editor_add_chapter
from fanic.ingest import editor_delete_chapter
from fanic.ingest import editor_delete_page
from fanic.ingest import editor_move_page
from fanic.ingest import editor_reorder_gallery
from fanic.ingest import editor_replace_page_image
from fanic.ingest import editor_update_chapter
from fanic.ingest import ingest_cbz
from fanic.ingest import ingest_editor_page
from fanic.ingest_progress import set_progress
from fanic.moderation import get_explicit_threshold
from fanic.repository import get_work
from fanic.repository import list_work_chapters
from fanic.repository import list_work_page_rows


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
        "status": (request.form.get("status", "").strip() if request.form.get("status", "").strip() else "in_progress"),
        "language": (request.form.get("language", "").strip() if request.form.get("language", "").strip() else "en"),
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
    editor_rating = (
        request.form.get("editor_rating", "").strip() if request.form.get("editor_rating", "").strip() else "Not Rated"
    )
    editor_status = (
        request.form.get("editor_status", "").strip()
        if request.form.get("editor_status", "").strip()
        else "in_progress"
    )
    editor_language = (
        request.form.get("editor_language", "").strip() if request.form.get("editor_language", "").strip() else "en"
    )

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
    upload_status_text: str,
    upload_status_kind: str,
    result_payload: dict[str, object] | None = None,
) -> ResponseLike:
    work_id = editor_state.get("editor_work_id", "")
    pages = list_work_page_rows(work_id) if work_id else []
    chapters = list_work_chapters(work_id) if work_id else []
    return render_upload_page(
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
        upload_status_text=upload_status_text,
        upload_status_kind=upload_status_kind,
        result_payload=result_payload,
    )


def _run_async_cbz_ingest(
    *,
    username: str,
    upload_token: str,
    cbz_path: Path,
    metadata_override_path: Path | None,
    cleanup_dir: Path,
) -> None:
    started_comic_ingest_session = False

    def _set_progress(
        *,
        stage: str,
        message: str,
        current: int = 0,
        total: int = 0,
        done: bool = False,
        ok: bool = False,
        work_id: str = "",
        redirect_to: str = "",
    ) -> None:
        if not upload_token:
            return
        set_progress(
            upload_token,
            stage=stage,
            message=message,
            current=current,
            total=total,
            done=done,
            ok=ok,
            work_id=work_id,
            redirect_to=redirect_to,
        )

    def on_queued(queue_position: int) -> None:
        _set_progress(
            stage="queued",
            message=f"Waiting in comic ingest queue (position {queue_position})",
            done=False,
            ok=False,
        )

    try:
        queue_allowed, _, queue_position = begin_comic_ingest_session(
            on_queued=on_queued,
        )
        if not queue_allowed:
            timeout_message = (
                f"Comic ingest queue timeout at position {queue_position}. Please retry."
                if queue_position > 0
                else "Comic ingest queue is full"
            )
            _set_progress(
                stage="throttled",
                message=timeout_message,
                done=True,
                ok=False,
            )
            return

        started_comic_ingest_session = True
        _set_progress(
            stage="starting",
            message="Starting import",
            done=False,
            ok=False,
        )

        result = ingest_cbz(
            cbz_path,
            metadata_override_path=metadata_override_path,
            uploader_username=username,
            progress_hook=(
                lambda stage, message, current, total: (
                    _set_progress(
                        stage=stage,
                        message=message,
                        current=current,
                        total=total,
                        done=False,
                        ok=False,
                    )
                    if upload_token
                    else None
                )
            ),
        )

        work_id = str(result.get("work_id", ""))
        _set_progress(
            stage="done",
            message="Import complete",
            done=True,
            ok=True,
            work_id=work_id,
            redirect_to=f"/comic/{work_id}" if work_id else "",
        )
    except ModerationBlockedError as exc:
        moderation = exc.moderation
        source_member = str(moderation.get("source_member", "") if moderation.get("source_member", "") else "")
        source_suffix = f" ({source_member})" if source_member else ""
        _set_progress(
            stage="blocked",
            message=f"CBZ import blocked by moderation policy{source_suffix}.",
            done=True,
            ok=False,
        )
    except Exception:
        _set_progress(
            stage="failed",
            message="Import failed",
            done=True,
            ok=False,
        )
    finally:
        if started_comic_ingest_session:
            end_comic_ingest_session()
        end_upload_session(username)
        shutil.rmtree(cleanup_dir, ignore_errors=True)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    _ = request_id(request, response)
    if request.path not in {"/comic/upload", "/comic/upload/"}:
        return text_error(response, "Not found", 404)

    if not enforce_https_termination(request, response):
        return response

    if not validate_csrf(request):
        return text_error(response, "Invalid CSRF token", 403)

    username = current_user(request)
    if username is None:
        return render_upload_page(
            request,
            response,
            upload_status_text="Login required before uploads.",
            upload_status_kind="error",
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
            return render_upload_page(
                request,
                response,
                upload_status_text="You must agree to the Terms and Conditions before uploading.",
                upload_status_kind="error",
            )

        if cbz_upload is None:
            return render_upload_page(
                request,
                response,
                upload_status_text="Please choose a CBZ file first.",
                upload_status_kind="error",
            )

        cbz_policy_error = validate_cbz_upload_policy(cbz_upload)
        if cbz_policy_error:
            return render_upload_page(
                request,
                response,
                upload_status_text=cbz_policy_error,
                upload_status_kind="error",
            )

        started_upload_session = False
        allowed, limit_code, retry_after = begin_upload_session(username)
        if not allowed:
            if upload_token:
                set_progress(
                    upload_token,
                    stage="throttled",
                    message="Upload temporarily throttled",
                    done=True,
                    ok=False,
                )
            message = (
                f"Too many upload requests. Please retry later (retry in {retry_after}s)."
                if limit_code == "upload_rate_limited"
                else "Too many concurrent uploads. Please wait for active uploads to finish."
            )
            return render_upload_page(
                request,
                response,
                upload_status_text=message,
                upload_status_kind="error",
            )

        task_dir: Path | None = None
        try:
            started_upload_session = True
            metadata = _collect_metadata_from_form(request)
            task_dir = Path(mkdtemp(prefix="fanic-comic-ingest-"))
            cbz_path = task_dir / Path(cbz_upload.filename if cbz_upload.filename else "upload.cbz").name
            cbz_upload.save(cbz_path)
            cbz_size_error = validate_saved_upload_size(
                cbz_path,
                MAX_CBZ_UPLOAD_BYTES,
                "CBZ upload",
            )
            if cbz_size_error:
                return render_upload_page(
                    request,
                    response,
                    upload_status_text=cbz_size_error,
                    upload_status_kind="error",
                )

            override_path: Path | None = None
            if metadata:
                override_path = task_dir / "metadata.json"
                _ = override_path.write_text(
                    json.dumps(metadata, ensure_ascii=True),
                    encoding="utf-8",
                )

            if upload_token:
                set_progress(
                    upload_token,
                    stage="queued",
                    message="Upload received. Waiting in comic ingest queue.",
                    done=False,
                    ok=False,
                )

            worker = threading.Thread(
                target=_run_async_cbz_ingest,
                kwargs={
                    "username": username,
                    "upload_token": upload_token,
                    "cbz_path": cbz_path,
                    "metadata_override_path": override_path,
                    "cleanup_dir": task_dir,
                },
                name="fanic-comic-ingest",
                daemon=True,
            )
            worker.start()

            return render_upload_page(
                request,
                response,
                upload_token=upload_token,
                upload_status_text="Upload accepted. Ingest is running in the background.",
                upload_status_kind="success",
                result_payload={
                    "ok": True,
                    "mode": "editor",
                    "uploaded_by": username,
                    "accepted": True,
                    "upload_token": upload_token,
                },
            )
        except Exception as exc:
            log_exception(
                request,
                code="ingest_failed",
                exc=exc,
                message="Browser ingest failed",
            )
            if upload_token:
                set_progress(
                    upload_token,
                    stage="failed",
                    message="Import request failed",
                    done=True,
                    ok=False,
                )
            return render_upload_page(
                request,
                response,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="CBZ import failed [ingest_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )
        finally:
            if started_upload_session and task_dir is None:
                end_upload_session(username)

    if action == "editor-add-page":
        editor_state = _editor_state_from_form(request)

        is_new_editor_draft = not editor_state.get("editor_work_id", "").strip()
        if is_new_editor_draft and not terms_accepted:
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text="You must agree to the Terms and Conditions before uploading.",
                upload_status_kind="error",
            )

        if page_upload is None:
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text="Choose an image page before uploading.",
                upload_status_kind="error",
            )

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=page_policy_error,
                upload_status_kind="error",
            )

        started_upload_session = False
        allowed, limit_code, retry_after = begin_upload_session(username)
        if not allowed:
            message = (
                f"Too many upload requests. Please retry later (retry in {retry_after}s)."
                if limit_code == "upload_rate_limited"
                else "Too many concurrent uploads. Please wait for active uploads to finish."
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=message,
                upload_status_kind="error",
            )

        editor_metadata: dict[str, object] = {
            "title": editor_state["editor_title"],
            "summary": editor_state["editor_summary"],
            "rating": editor_state["editor_rating"],
            "status": editor_state["editor_status"],
            "language": editor_state["editor_language"],
        }

        try:
            started_upload_session = True
            with TemporaryDirectory() as temp_dir:
                page_path = Path(temp_dir) / Path(page_upload.filename if page_upload.filename else "page.png").name
                page_upload.save(page_path)
                page_size_error = validate_saved_upload_size(
                    page_path,
                    MAX_PAGE_UPLOAD_BYTES,
                    "Page upload",
                )
                if page_size_error:
                    return _render_editor_result(
                        request,
                        response,
                        editor_state,
                        upload_status_text=page_size_error,
                        upload_status_kind="error",
                    )
                result = ingest_editor_page(
                    image_path=page_path,
                    metadata=editor_metadata,
                    uploader_username=username,
                    work_id=(editor_state["editor_work_id"] if editor_state["editor_work_id"] else None),
                )

            work_id = str(result.get("work_id", ""))
            editor_state["editor_work_id"] = work_id
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=(
                    "Page uploaded to comic draft."
                    if not bool(result.get("rating_auto_elevated"))
                    else (
                        "Page uploaded to comic draft. Rating auto-updated from "
                        f"{result.get('rating_before')} to {result.get('rating_after')} based on moderation."
                    )
                ),
                upload_status_kind="success",
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
                upload_status_text="Editor upload blocked by moderation policy.",
                upload_status_kind="error",
                result_payload={
                    "ok": False,
                    "mode": "editor",
                    "blocked": True,
                    "explicit_threshold": get_explicit_threshold(),
                    "error": "moderation_blocked",
                    "message": admin_aware_detail(
                        request,
                        public_detail="Blocked by moderation policy",
                        exc=exc,
                    ),
                    "moderation": {
                        "allow": bool(moderation.get("allow", False)),
                        "style": str(moderation.get("style", "unknown")),
                        "style_debug": moderation.get("style_debug", {}),
                        "style_confidences": moderation.get("style_confidences", {}),
                        "nsfw_score": float(
                            moderation.get("nsfw_score", 0.0) if moderation.get("nsfw_score", 0.0) else 0.0
                        ),
                        "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                        "reasons": reasons,
                    },
                },
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_add_page_failed",
                exc=exc,
                message="Editor add page failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Editor upload failed [editor_add_page_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )
        finally:
            if started_upload_session:
                end_upload_session(username)

    if action == "editor-replace-page":
        editor_state = _editor_state_from_form(request)
        if page_upload is None:
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text="Choose an image to replace the page.",
                upload_status_kind="error",
            )

        page_policy_error = validate_page_upload_policy(page_upload)
        if page_policy_error:
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=page_policy_error,
                upload_status_kind="error",
            )

        started_upload_session = False
        allowed, limit_code, retry_after = begin_upload_session(username)
        if not allowed:
            message = (
                f"Too many upload requests. Please retry later (retry in {retry_after}s)."
                if limit_code == "upload_rate_limited"
                else "Too many concurrent uploads. Please wait for active uploads to finish."
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=message,
                upload_status_kind="error",
            )

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
                    return _render_editor_result(
                        request,
                        response,
                        editor_state,
                        upload_status_text=page_size_error,
                        upload_status_kind="error",
                    )
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
                upload_status_text=(
                    "Page replaced."
                    if not bool(result.get("rating_auto_elevated"))
                    else (
                        "Page replaced. Rating auto-updated from "
                        f"{result.get('rating_before')} to {result.get('rating_after')} based on moderation."
                    )
                ),
                upload_status_kind="success",
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
                upload_status_text="Replace blocked by moderation policy.",
                upload_status_kind="error",
                result_payload={
                    "ok": False,
                    "mode": "editor",
                    "blocked": True,
                    "explicit_threshold": get_explicit_threshold(),
                    "error": "moderation_blocked",
                    "message": admin_aware_detail(
                        request,
                        public_detail="Blocked by moderation policy",
                        exc=exc,
                    ),
                    "moderation": {
                        "allow": bool(moderation.get("allow", False)),
                        "style": str(moderation.get("style", "unknown")),
                        "style_debug": moderation.get("style_debug", {}),
                        "style_confidences": moderation.get("style_confidences", {}),
                        "nsfw_score": float(
                            moderation.get("nsfw_score", 0.0) if moderation.get("nsfw_score", 0.0) else 0.0
                        ),
                        "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                        "reasons": reasons,
                    },
                },
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_replace_page_failed",
                exc=exc,
                message="Editor replace page failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Replace failed [editor_replace_page_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )
        finally:
            if started_upload_session:
                end_upload_session(username)

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
                upload_status_text="Page deleted.",
                upload_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_delete_page_failed",
                exc=exc,
                message="Editor delete page failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Delete failed [editor_delete_page_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
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
                upload_status_text="Page reordered.",
                upload_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_move_page_failed",
                exc=exc,
                message="Editor move page failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Reorder failed [editor_move_page_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
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
                upload_status_text="Gallery order saved. Page order and chapter assignments updated.",
                upload_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_reorder_gallery_failed",
                exc=exc,
                message="Editor reorder gallery failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Reorder failed [editor_reorder_gallery_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )

    if action == "editor-add-chapter":
        editor_state = _editor_state_from_form(request)
        try:
            title = (
                request.form.get("chapter_title", "").strip()
                if request.form.get("chapter_title", "").strip()
                else "Untitled Chapter"
            )
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
                upload_status_text="Chapter added.",
                upload_status_kind="success",
                result_payload={"ok": True, "mode": "editor", "result": result},
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_add_chapter_failed",
                exc=exc,
                message="Editor add chapter failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Add chapter failed [editor_add_chapter_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
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
                upload_status_text="Chapter deleted.",
                upload_status_kind="success",
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_delete_chapter_failed",
                exc=exc,
                message="Editor delete chapter failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Delete chapter failed [editor_delete_chapter_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )

    if action == "editor-update-chapter":
        editor_state = _editor_state_from_form(request)
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
                upload_status_text="Chapter updated.",
                upload_status_kind="success",
            )
        except Exception as exc:
            log_exception(
                request,
                code="editor_update_chapter_failed",
                exc=exc,
                message="Editor update chapter failed",
            )
            return _render_editor_result(
                request,
                response,
                editor_state,
                upload_status_text=admin_aware_detail(
                    request,
                    public_detail="Update chapter failed [editor_update_chapter_failed].",
                    exc=exc,
                ),
                upload_status_kind="error",
            )

    return render_upload_page(request, response)
