from pathlib import Path


def test_comic_upload_progress_js_uses_comic_ingest_endpoint() -> None:
    script_path = Path("static/comic-upload-progress.js")
    script_text = script_path.read_text(encoding="utf-8")

    assert "/api/comic-ingest/progress?token=" in script_text
    assert "comic-ingest-${Date.now()}-" in script_text

    assert "/api/ingest/progress?token=" not in script_text
    assert "return `ingest-${Date.now()}-" not in script_text
