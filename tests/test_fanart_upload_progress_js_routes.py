from pathlib import Path

from fanic.settings import ASSET_VERSIONS


def _load_fanart_upload_progress_script_text() -> str:
    progress_version = ASSET_VERSIONS.get("fanart-upload-progress", "0")
    candidate_paths = [
        Path("frontend/fanart-upload-progress.ts"),
        Path(f"/mnt/storage/static/fanart-upload-progress.v{progress_version}.js"),
        Path("static/fanart-upload-progress.js"),
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    searched = ", ".join(str(path) for path in candidate_paths)
    raise FileNotFoundError(f"fanart upload progress script not found in: {searched}")


def test_fanart_upload_progress_js_uses_fanart_ingest_endpoint() -> None:
    script_text = _load_fanart_upload_progress_script_text()

    assert "/api/fanart-ingest/progress?token=" in script_text
    assert "fanart-ingest-${Date.now()}-" in script_text

    assert "/api/comic-ingest/progress?token=" not in script_text
    assert "comic-ingest-${Date.now()}-" not in script_text
