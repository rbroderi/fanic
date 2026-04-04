from pathlib import Path

from fanic.settings import ASSET_VERSIONS


def _load_comic_upload_progress_script_text() -> str:
    progress_version = ASSET_VERSIONS.get("comic-upload-progress", "0")
    candidate_paths = [
        Path("frontend/comic-upload-progress.ts"),
        Path(f"/mnt/storage/static/comic-upload-progress.v{progress_version}.js"),
        Path("static/comic-upload-progress.js"),
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    searched = ", ".join(str(path) for path in candidate_paths)
    raise FileNotFoundError(f"comic upload progress script not found in: {searched}")


def test_comic_upload_progress_js_uses_comic_ingest_endpoint() -> None:
    script_text = _load_comic_upload_progress_script_text()

    assert "/api/comic-ingest/progress?token=" in script_text
    assert "comic-ingest-${Date.now()}-" in script_text

    assert "/api/ingest/progress?token=" not in script_text
    assert "return `ingest-${Date.now()}-" not in script_text
