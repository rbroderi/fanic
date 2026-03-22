from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    current_user,
    json_response,
    route_tail,
)
from fanic.ingest import (
    ModerationBlockedError,
    extract_comicinfo_metadata_from_cbz,
    ingest_cbz,
)
from fanic.ingest_progress import get_progress, set_progress
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


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    tail = route_tail(request, ["api", "ingest"])
    if tail is None:
        return json_response(response, {"detail": "Not found"}, 404)

    username = current_user(request)
    if username is None:
        return json_response(response, {"detail": "Login required"}, 401)

    if tail == ["metadata"]:
        cbz_upload = request.files.get("cbz")
        if cbz_upload is None:
            return json_response(response, {"detail": "cbz file is required"}, 400)

        try:
            with TemporaryDirectory() as temp_dir:
                cbz_path = (
                    Path(temp_dir) / Path(cbz_upload.filename or "upload.cbz").name
                )
                cbz_upload.save(cbz_path)
                metadata = extract_comicinfo_metadata_from_cbz(cbz_path)

            return json_response(response, {"ok": True, "metadata": metadata})
        except Exception as exc:
            return json_response(
                response, {"detail": f"Metadata parse failed: {exc}"}, 400
            )

    if tail == ["progress"]:
        token = request.args.get("token", "").strip()
        if not token:
            return json_response(response, {"detail": "token is required"}, 400)
        progress = get_progress(token)
        if progress is None:
            return json_response(response, {"ok": False, "found": False}, 404)
        return json_response(
            response, {"ok": True, "found": True, "progress": progress}
        )

    if tail != []:
        return json_response(response, {"detail": "Not found"}, 404)

    cbz_upload = request.files.get("cbz")
    if cbz_upload is None:
        return json_response(response, {"detail": "cbz file is required"}, 400)

    upload_token = request.form.get("upload_token", "").strip()

    try:
        if upload_token:
            set_progress(upload_token, stage="starting", message="Starting import")

        form_metadata = _collect_metadata_from_form(request)
        with TemporaryDirectory() as temp_dir:
            cbz_path = Path(temp_dir) / Path(cbz_upload.filename or "upload.cbz").name
            cbz_upload.save(cbz_path)

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
            reasons = [str(reason) for reason in reasons_obj]

        return json_response(
            response,
            {
                "ok": False,
                "mode": "editor",
                "detail": "Ingest blocked by moderation policy",
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
                    "source_member": str(moderation.get("source_member", "") or ""),
                },
            },
            400,
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
        return json_response(response, {"detail": f"Ingest failed: {exc}"}, 400)
