from __future__ import annotations

import json
import secrets
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
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
    editor_add_chapter,
    editor_delete_chapter,
    editor_delete_page,
    editor_move_page,
    editor_replace_page_image,
    editor_update_chapter,
    extract_comicinfo_metadata_from_cbz,
    ingest_cbz,
    ingest_editor_page,
)
from fanic.paths import DATA_ROOT
from fanic.repository import get_work, list_work_chapters, list_work_page_rows

_UPLOAD_STAGE_DIR = DATA_ROOT / "upload_staging"
_UPLOAD_JOB_DIR = DATA_ROOT / "upload_jobs"
_UPLOAD_TTL_SECONDS = 60 * 60
_INGEST_WORKERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fanic-ingest")


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _has_selected_file(upload: object | None) -> bool:
    if upload is None:
        return False
    filename = getattr(upload, "filename", None)
    return isinstance(filename, str) and bool(filename.strip())


def _ensure_stage_dir() -> None:
    _UPLOAD_STAGE_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_job_dir() -> None:
    _UPLOAD_JOB_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup_stale_uploads(now: float) -> None:
    if not _UPLOAD_STAGE_DIR.exists():
        return
    for path in _UPLOAD_STAGE_DIR.glob("*.cbz"):
        try:
            if now - path.stat().st_mtime > _UPLOAD_TTL_SECONDS:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def _new_upload_token() -> str:
    return secrets.token_urlsafe(24)


def _stage_upload(upload) -> tuple[str, Path]:
    _ensure_stage_dir()
    token = _new_upload_token()
    staged_path = _UPLOAD_STAGE_DIR / f"{token}.cbz"
    upload.save(staged_path)
    return token, staged_path


def _path_for_token(token: str) -> Path | None:
    if not token:
        return None
    if any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for ch in token
    ):
        return None
    path = _UPLOAD_STAGE_DIR / f"{token}.cbz"
    return path if path.exists() else None


def _process_queued_ingest(
    cbz_path: Path,
    metadata_path: Path,
    uploader_username: str,
    job_dir: Path,
) -> None:
    try:
        _ = ingest_cbz(cbz_path, metadata_path, uploader_username=uploader_username)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _enqueue_ingest_job(
    *,
    cbz_upload,
    staged_path: Path | None,
    metadata: dict[str, object],
    uploader_username: str,
) -> str:
    _ensure_job_dir()
    job_id = _new_upload_token()
    job_dir = _UPLOAD_JOB_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    cbz_path = job_dir / "upload.cbz"
    metadata_path = job_dir / "metadata.json"

    if staged_path is not None:
        _ = shutil.copy2(staged_path, cbz_path)
    else:
        cbz_upload.save(cbz_path)

    _ = metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True),
        encoding="utf-8",
    )

    _INGEST_WORKERS.submit(
        _process_queued_ingest,
        cbz_path,
        metadata_path,
        uploader_username,
        job_dir,
    )
    return job_id


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
    raw_cbz_upload = request.files.get("cbz")
    cbz_upload = raw_cbz_upload if _has_selected_file(raw_cbz_upload) else None
    raw_page_upload = request.files.get("page_image")
    page_upload = raw_page_upload if _has_selected_file(raw_page_upload) else None
    upload_token = request.form.get("upload_token", "").strip()
    now = time.time()
    _cleanup_stale_uploads(now)

    if action == "load-metadata":
        if cbz_upload is None:
            return render_ingest_page(
                request,
                response,
                ingest_status="Please choose a CBZ file first.",
                ingest_status_kind="error",
            )

        try:
            token, staged_path = _stage_upload(cbz_upload)
            metadata = extract_comicinfo_metadata_from_cbz(staged_path)
            if not str(metadata.get("title", "")).strip():
                fallback_title = Path(cbz_upload.filename or "").stem.strip()
                if fallback_title:
                    metadata["title"] = fallback_title

            return render_ingest_page(
                request,
                response,
                metadata=metadata,
                show_metadata_form=True,
                upload_token=token,
                ingest_status="Metadata loaded from ComicInfo.xml. Review fields and click Ingest comic.",
                ingest_status_kind="success",
            )
        except Exception as exc:
            return render_ingest_page(
                request,
                response,
                show_metadata_form=True,
                upload_token=upload_token,
                ingest_status=f"Failed to parse ComicInfo.xml: {exc}",
                ingest_status_kind="error",
            )

    if action == "ingest":
        metadata = _collect_metadata_from_form(request)

        staged_path = _path_for_token(upload_token)
        if cbz_upload is None and staged_path is None:
            return render_ingest_page(
                request,
                response,
                metadata=metadata,
                show_metadata_form=True,
                upload_token=upload_token,
                ingest_status="Please choose a CBZ file and load metadata first.",
                ingest_status_kind="error",
            )

        try:
            if staged_path is None and cbz_upload is None:
                raise ValueError("Upload token is missing or expired")

            job_id = _enqueue_ingest_job(
                cbz_upload=cbz_upload,
                staged_path=staged_path,
                metadata=metadata,
                uploader_username=username,
            )

            if staged_path is not None:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    pass

            return render_ingest_page(
                request,
                response,
                metadata=metadata,
                show_metadata_form=True,
                upload_token="",
                ingest_status="Comic queued for processing. It will be added as soon as it finishes processing.",
                ingest_status_kind="success",
                result_payload={
                    "ok": True,
                    "queued": True,
                    "job_id": job_id,
                    "uploaded_by": username,
                },
            )
        except Exception as exc:
            return render_ingest_page(
                request,
                response,
                metadata=metadata,
                show_metadata_form=True,
                upload_token=upload_token,
                ingest_status=f"Ingest failed: {exc}",
                ingest_status_kind="error",
            )

    if action == "editor-add-page":
        editor_state = _editor_state_from_form(request)

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
