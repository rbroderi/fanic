import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from fanic.cylinder_sites.common import MAX_CBZ_UPLOAD_BYTES
from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import admin_aware_detail
from fanic.cylinder_sites.common import begin_comic_ingest_session
from fanic.cylinder_sites.common import begin_upload_session
from fanic.cylinder_sites.common import current_user
from fanic.cylinder_sites.common import end_comic_ingest_session
from fanic.cylinder_sites.common import end_upload_session
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import log_exception
from fanic.cylinder_sites.common import request_id
from fanic.cylinder_sites.common import route_tail
from fanic.cylinder_sites.common import stable_api_error
from fanic.cylinder_sites.common import upload_policy_error_info
from fanic.cylinder_sites.common import validate_cbz_upload_policy
from fanic.cylinder_sites.common import validate_saved_upload_size
from fanic.ingest import ModerationBlockedError
from fanic.ingest import extract_comicinfo_metadata_from_cbz
from fanic.ingest import ingest_cbz
from fanic.ingest_progress import get_progress
from fanic.ingest_progress import set_progress
from fanic.moderation import get_explicit_threshold


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _collect_metadata_from_form(request: RequestLike) -> dict[str, object]:
    metadata: dict[str, object] = {
        "title": request.form.get("title", "").strip(),
        "summary": request.form.get("summary", "").strip(),
        "rating": request.form.get("rating", "").strip(),
        "warnings": _csv(request.form.get("warnings", "")),
        "status": request.form.get("status", "").strip(),
        "language": request.form.get("language", "").strip(),
        "series": request.form.get("series", "").strip(),
        "series_index": request.form.get("series_index", "").strip(),
        "published_at": request.form.get("published_at", "").strip(),
        "fandoms": _csv(request.form.get("fandoms", "")),
        "relationships": _csv(request.form.get("relationships", "")),
        "characters": _csv(request.form.get("characters", "")),
        "freeform_tags": _csv(request.form.get("freeform_tags", "")),
    }

    # Drop empty values to let ingest defaults fill naturally.
    clean: dict[str, object] = {}
    for key, value in metadata.items():
        if isinstance(value, str) and value:
            clean[key] = value
        elif isinstance(value, list) and value:
            clean[key] = value

    return clean


def _coerce_float(value: object, default: float = 0.0) -> float:
    if not isinstance(value, (str, int, float)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    _ = request_id(request, response)
    tail = route_tail(request, ["api", "comic-ingest"])
    if tail is None:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    if username is None:
        return json_response(response, {"detail": "Login required"}, 401)

    if tail == ["metadata"]:
        cbz_upload = request.files.get("cbz")
        if cbz_upload is None:
            return json_response(response, {"detail": "cbz file is required"}, 400)

        cbz_policy_error = validate_cbz_upload_policy(cbz_upload)
        if cbz_policy_error:
            error_code, status_code = upload_policy_error_info(cbz_policy_error)
            return json_response(
                response,
                {"detail": cbz_policy_error, "error": error_code},
                status_code,
            )

        started_comic_ingest_session = False
        queue_allowed, queue_retry_after, queue_position = begin_comic_ingest_session()
        if not queue_allowed:
            return json_response(
                response,
                {
                    "ok": False,
                    "error": "comic_ingest_queue_timeout",
                    "detail": "Comic ingest queue is full. Please retry shortly.",
                    "retry_after": queue_retry_after,
                    "queue_position": queue_position,
                    "request_id": request_id(request, response),
                },
                429,
            )

        started_comic_ingest_session = True
        started_upload_session = False
        allowed, limit_code, retry_after = begin_upload_session(username)
        if not allowed:
            if limit_code == "upload_rate_limited":
                return json_response(
                    response,
                    {
                        "ok": False,
                        "error": limit_code,
                        "detail": "Too many upload requests. Please retry later.",
                        "retry_after": retry_after,
                        "request_id": request_id(request, response),
                    },
                    429,
                )
            return json_response(
                response,
                {
                    "ok": False,
                    "error": limit_code,
                    "detail": "Too many concurrent uploads. Please wait for active uploads to finish.",
                    "request_id": request_id(request, response),
                },
                429,
            )

        try:
            started_upload_session = True
            with TemporaryDirectory() as temp_dir:
                cbz_path = Path(temp_dir) / Path(cbz_upload.filename if cbz_upload.filename else "upload.cbz").name
                cbz_upload.save(cbz_path)
                cbz_size_error = validate_saved_upload_size(
                    cbz_path,
                    MAX_CBZ_UPLOAD_BYTES,
                    "CBZ upload",
                )
                if cbz_size_error:
                    error_code, status_code = upload_policy_error_info(cbz_size_error)
                    return json_response(
                        response,
                        {"detail": cbz_size_error, "error": error_code},
                        status_code,
                    )
                metadata = extract_comicinfo_metadata_from_cbz(cbz_path)

            return json_response(response, {"ok": True, "metadata": metadata})
        except Exception as exc:
            log_exception(
                request,
                code="metadata_parse_failed",
                exc=exc,
                message="Metadata parse failure",
            )
            return stable_api_error(
                request,
                response,
                error="metadata_parse_failed",
                public_detail="Unable to parse metadata from the uploaded archive",
                status_code=400,
                exc=exc,
            )
        finally:
            if started_upload_session:
                end_upload_session(username)
            if started_comic_ingest_session:
                end_comic_ingest_session()

    if tail == ["progress"]:
        token = request.args.get("token", "").strip()
        if not token:
            return json_response(response, {"detail": "token is required"}, 400)
        progress = get_progress(token)
        if progress is None:
            return json_response(response, {"ok": False, "found": False}, 404)
        return json_response(response, {"ok": True, "found": True, "progress": progress})

    if tail != []:
        return json_response(response, {"detail": "Not found"}, 404)

    cbz_upload = request.files.get("cbz")
    if cbz_upload is None:
        return json_response(response, {"detail": "cbz file is required"}, 400)

    cbz_policy_error = validate_cbz_upload_policy(cbz_upload)
    if cbz_policy_error:
        error_code, status_code = upload_policy_error_info(cbz_policy_error)
        return json_response(
            response,
            {"detail": cbz_policy_error, "error": error_code},
            status_code,
        )

    upload_token = request.form.get("upload_token", "").strip()

    def on_queued(queue_position: int) -> None:
        if not upload_token:
            return
        set_progress(
            upload_token,
            stage="queued",
            message=f"Waiting in comic ingest queue (position {queue_position})",
            done=False,
            ok=False,
        )

    started_comic_ingest_session = False
    queue_allowed, queue_retry_after, queue_position = begin_comic_ingest_session(
        on_queued=on_queued,
    )
    if not queue_allowed:
        if upload_token:
            set_progress(
                upload_token,
                stage="throttled",
                message=(
                    f"Comic ingest queue timeout at position {queue_position}. Please retry."
                    if queue_position > 0
                    else "Comic ingest queue is full"
                ),
                done=True,
                ok=False,
            )
        return json_response(
            response,
            {
                "ok": False,
                "error": "comic_ingest_queue_timeout",
                "detail": "Comic ingest queue is full. Please retry shortly.",
                "retry_after": queue_retry_after,
                "queue_position": queue_position,
                "request_id": request_id(request, response),
            },
            429,
        )

    started_comic_ingest_session = True
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
        if limit_code == "upload_rate_limited":
            return json_response(
                response,
                {
                    "ok": False,
                    "error": limit_code,
                    "detail": "Too many upload requests. Please retry later.",
                    "retry_after": retry_after,
                    "request_id": request_id(request, response),
                },
                429,
            )
        return json_response(
            response,
            {
                "ok": False,
                "error": limit_code,
                "detail": "Too many concurrent uploads. Please wait for active uploads to finish.",
                "request_id": request_id(request, response),
            },
            429,
        )

    try:
        started_upload_session = True
        if upload_token:
            set_progress(upload_token, stage="starting", message="Starting import")

        form_metadata = _collect_metadata_from_form(request)
        with TemporaryDirectory() as temp_dir:
            cbz_path = Path(temp_dir) / Path(cbz_upload.filename if cbz_upload.filename else "upload.cbz").name
            cbz_upload.save(cbz_path)
            cbz_size_error = validate_saved_upload_size(
                cbz_path,
                MAX_CBZ_UPLOAD_BYTES,
                "CBZ upload",
            )
            if cbz_size_error:
                error_code, status_code = upload_policy_error_info(cbz_size_error)
                return json_response(
                    response,
                    {"detail": cbz_size_error, "error": error_code},
                    status_code,
                )

            metadata_path: Path | None = None
            if form_metadata:
                metadata_path = Path(temp_dir) / "metadata.json"
                _ = metadata_path.write_text(
                    json.dumps(form_metadata, ensure_ascii=True),
                    encoding="utf-8",
                )

            result = ingest_cbz(
                cbz_path,
                metadata_override_path=metadata_path,
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

        return json_response(
            response,
            {
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
            reasons = [str(reason) for reason in cast(list[object], reasons_obj)]

        nsfw_score = _coerce_float(moderation.get("nsfw_score", 0.0), 0.0)

        return json_response(
            response,
            {
                "ok": False,
                "mode": "editor",
                "detail": "Ingest blocked by moderation policy",
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
                    "nsfw_score": nsfw_score,
                    "nsfw_confidences": moderation.get("nsfw_confidences", {}),
                    "reasons": reasons,
                    "source_member": str(
                        moderation.get("source_member", "") if moderation.get("source_member", "") else ""
                    ),
                },
            },
            400,
        )
    except Exception as exc:
        log_exception(
            request,
            code="ingest_failed",
            exc=exc,
            message="Ingest execution failure",
        )
        if upload_token:
            set_progress(
                upload_token,
                stage="failed",
                message="Import failed",
                done=True,
                ok=False,
            )
        return stable_api_error(
            request,
            response,
            error="ingest_failed",
            public_detail="Unable to ingest the uploaded archive",
            status_code=400,
            exc=exc,
        )
    finally:
        if started_upload_session:
            end_upload_session(username)
        if started_comic_ingest_session:
            end_comic_ingest_session()
