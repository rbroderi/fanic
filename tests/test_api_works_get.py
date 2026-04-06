import xml.etree.ElementTree as StdET
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest


def test_build_comicinfo_xml_includes_extended_fanic_metadata(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.get.py",
        "fanicsite_api_comic_ex_get_comicinfo_export_test",
    )
    monkeypatch.setattr(module, "ET_ANY", StdET)

    work: dict[str, object] = {
        "id": "work-123",
        "slug": "sample-work",
        "title": "Sample Work",
        "summary": "Summary",
        "language": "en",
        "series_name": "Metro Cases",
        "series_index": 2,
        "creators": ["Alice Artist", "Bob Writer"],
        "page_count": 12,
        "rating": "Teen And Up Audiences",
        "status": "complete",
        "cover_page_index": 4,
        "published_at": "2026-03-09",
        "tags": [
            {"name": "Nick Wilde", "type": "character"},
            {"name": "Detective AU", "type": "freeform"},
            {"name": "Zootopia", "type": "fandom"},
            {"name": "Nick Wilde/Judy Hopps", "type": "relationship"},
            {"name": "F/F", "type": "category"},
            {"name": "Graphic Violence", "type": "archive_warning"},
        ],
    }

    pages: list[dict[str, object]] = [
        {"page_index": 1, "width": 1200, "height": 1800},
        {"page_index": 2, "width": 1200, "height": 1800},
    ]

    xml_text = module._build_comicinfo_xml(work, pages)

    assert "<Writer>Alice Artist, Bob Writer</Writer>" in xml_text
    assert "<Count>12</Count>" in xml_text
    assert "<PageCount>12</PageCount>" in xml_text
    assert "<Genre>F/F</Genre>" in xml_text
    assert "<Characters>Nick Wilde</Characters>" in xml_text
    assert "<StoryArc>Nick Wilde/Judy Hopps</StoryArc>" in xml_text
    assert "<SeriesGroup>Zootopia</SeriesGroup>" in xml_text
    assert "<AgeRating>Teen</AgeRating>" in xml_text
    assert "<Pages>" in xml_text
    assert 'Page Image="0" Type="Story" ImageWidth="1200" ImageHeight="1800"' in xml_text
    assert 'Page Image="1" Type="Story" ImageWidth="1200" ImageHeight="1800"' in xml_text
    assert "fanic_meta=" in xml_text
    assert '"id": "work-123"' in xml_text
    assert '"slug": "sample-work"' in xml_text
    assert '"status": "complete"' in xml_text
    assert '"cover_page_index": 4' in xml_text


def test_versioned_archive_path_and_download_filename(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.get.py",
        "fanicsite_api_comic_ex_get_versioned_archive_test",
    )

    monkeypatch.setattr(module, "CBZ_DIR", Path("/tmp/fanic-cbz"))

    work: dict[str, object] = {
        "slug": "my-work",
        "cbz_path": "",
    }
    export_key = "version:20260406T123456_000001Z"

    archive_path = module._resolve_archive_path("work-123", work, export_key)
    filename = module._download_archive_filename("work-123", work, export_key)

    assert archive_path == Path("/tmp/fanic-cbz/work-123.version-20260406t123456-000001z.cbz")
    assert filename == "my-work.version-20260406t123456-000001z.cbz"


def test_archive_media_key_and_cdn_url(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.get.py",
        "fanicsite_api_comic_ex_get_archive_cdn_url_test",
    )

    class _FakeMediaService:
        settings: SimpleNamespace

        def __init__(self) -> None:
            self.settings = SimpleNamespace(media_cdn_base_url="https://media.fanic.media")

        def public_path_for_key(self, key: str) -> str:
            return f"/static/{key}"

        def media_url(self, path_or_key: str) -> str:
            return f"https://fanic.media{path_or_key}"

    monkeypatch.setattr(module, "_MEDIA_SERVICE", _FakeMediaService())

    key = module._archive_media_key(
        "work-123",
        "my-work.version-20260406t123456-000001z.cbz",
    )
    url = module._archive_cdn_url(key)

    assert key == "work-123/downloads/my-work.version-20260406t123456-000001z.cbz"
    assert url == "https://media.fanic.media/static/work-123/downloads/my-work.version-20260406t123456-000001z.cbz"


def test_publish_download_archive_uploads_when_missing(
    load_route_module: Callable[[str, str], ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/comic.ex.get.py",
        "fanicsite_api_comic_ex_get_publish_archive_test",
    )

    captured: dict[str, object] = {}

    class _FakeMediaService:
        settings: SimpleNamespace

        def __init__(self) -> None:
            self.settings = SimpleNamespace(media_cdn_base_url="https://media.fanic.media")

        def exists(self, key: str) -> bool:
            _ = key
            return False

        def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
            captured["key"] = key
            captured["content"] = content
            captured["content_type"] = content_type

        def public_path_for_key(self, key: str) -> str:
            return f"/static/{key}"

        def media_url(self, path_or_key: str) -> str:
            return f"https://fanic.media{path_or_key}"

    monkeypatch.setattr(module, "_MEDIA_SERVICE", _FakeMediaService())

    archive_path = tmp_path / "work-123.version-1.cbz"
    archive_path.write_bytes(b"cbz-bytes")

    media_key, url = module._publish_download_archive(
        "work-123",
        {"slug": "my-work"},
        archive_path,
        "version-1",
    )

    assert media_key == "work-123/downloads/my-work.version-1.cbz"
    assert url == "https://media.fanic.media/static/work-123/downloads/my-work.version-1.cbz"
    assert captured["key"] == media_key
    assert captured["content"] == b"cbz-bytes"
    assert captured["content_type"] == "application/vnd.comicbook+zip"
