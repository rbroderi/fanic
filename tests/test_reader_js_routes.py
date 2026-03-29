from pathlib import Path


def test_reader_js_uses_comic_api_routes() -> None:
    reader_js_path = Path("static/reader.js")
    reader_js_text = reader_js_path.read_text(encoding="utf-8")

    assert "/api/comic/${state.workId}/progress" in reader_js_text
    assert "/api/comic/${state.workId}/bookmark" in reader_js_text
    assert "`/comic/${state.workId}`" in reader_js_text

    assert "/api/works/${state.workId}/progress" not in reader_js_text
    assert "/api/works/${state.workId}/bookmark" not in reader_js_text
    assert "`/works/${state.workId}`" not in reader_js_text
