from pathlib import Path

from fanic.settings import ASSET_VERSIONS


def _load_reader_script_text() -> str:
    reader_version = ASSET_VERSIONS.get("reader", "0")
    candidate_paths = [
        Path("frontend/reader.ts"),
        Path(f"/mnt/storage/static/reader.v{reader_version}.js"),
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
