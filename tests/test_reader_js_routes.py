from pathlib import Path


def _load_reader_script_text() -> str:
    candidate_paths = [
        Path("frontend/reader.ts"),
        Path("/mnt/storage/static/reader.js"),
        Path("static/reader.js"),
    ]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    searched = ", ".join(str(path) for path in candidate_paths)
    raise FileNotFoundError(f"reader script not found in: {searched}")


def test_reader_js_uses_comic_api_routes() -> None:
    reader_js_text = _load_reader_script_text()

    assert "/api/comic/${state.workId}/progress" in reader_js_text
    assert "/api/comic/${state.workId}/bookmark" in reader_js_text
    assert "`/comic/${state.workId}`" in reader_js_text

    assert "/api/works/${state.workId}/progress" not in reader_js_text
    assert "/api/works/${state.workId}/bookmark" not in reader_js_text
    assert "`/works/${state.workId}`" not in reader_js_text
