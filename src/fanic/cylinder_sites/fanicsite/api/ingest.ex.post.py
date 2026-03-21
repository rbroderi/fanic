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
from fanic.ingest import extract_comicinfo_metadata_from_cbz, ingest_cbz


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

    if tail != []:
        return json_response(response, {"detail": "Not found"}, 404)

    cbz_upload = request.files.get("cbz")
    if cbz_upload is None:
        return json_response(response, {"detail": "cbz file is required"}, 400)

    try:
        form_metadata = _collect_metadata_from_form(request)
        with TemporaryDirectory() as temp_dir:
            cbz_path = Path(temp_dir) / Path(cbz_upload.filename or "upload.cbz").name
            cbz_upload.save(cbz_path)

            metadata_path = Path(temp_dir) / "metadata.json"
            _ = metadata_path.write_text(
                json.dumps(form_metadata, ensure_ascii=True),
                encoding="utf-8",
            )
            result = ingest_cbz(cbz_path, metadata_path)

        return json_response(
            response,
            {
                "ok": True,
                "uploaded_by": username,
                "result": result,
            },
        )
    except Exception as exc:
        return json_response(response, {"detail": f"Ingest failed: {exc}"}, 400)
