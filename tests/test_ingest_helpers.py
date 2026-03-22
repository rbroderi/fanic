from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from typing import Any
from typing import cast

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
INGEST_PATH = ROOT / "src" / "fanic" / "ingest.py"


def _load_ingest_with_stubs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> ModuleType:
    def noop(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        return None

    def get_settings_obj() -> SimpleNamespace:
        return SimpleNamespace(
            image_avif_quality=75,
            thumbnail_avif_quality=60,
        )

    def get_explicit_threshold() -> float:
        return 0.8

    def moderate_image(path: str) -> dict[str, object]:
        _ = path
        return {
            "allow": True,
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.0,
            "nsfw_confidences": {"sfw": 1.0, "explicit": 0.0},
        }

    def moderate_image_bytes(data: bytes, suffix: str = ".png") -> dict[str, object]:
        _ = (data, suffix)
        return {
            "allow": True,
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.0,
            "nsfw_confidences": {"sfw": 1.0, "explicit": 0.0},
        }

    def suggested_rating_for_nsfw(score: float) -> str | None:
        return "Explicit" if score >= 0.8 else None

    def make_chapter(*args: object, **kwargs: object) -> dict[str, object]:
        _ = (args, kwargs)
        return {"id": 1}

    def make_snapshot(*args: object, **kwargs: object) -> dict[str, object]:
        _ = (args, kwargs)
        return {"version_id": "v1"}

    def always_true(*args: object, **kwargs: object) -> bool:
        _ = (args, kwargs)
        return True

    def get_work_none(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        return None

    def empty_list(*args: object, **kwargs: object) -> list[object]:
        _ = (args, kwargs)
        return []

    def slugify_value(value: object) -> str:
        return str(value).strip().lower().replace(" ", "-")

    def get_connection_none() -> None:
        return None

    settings_stub = ModuleType("fanic.settings")
    setattr(settings_stub, "CBZ_DIR", tmp_path / "cbz")
    setattr(settings_stub, "WORKS_DIR", tmp_path / "works")
    setattr(settings_stub, "ensure_storage_dirs", noop)
    setattr(settings_stub, "get_settings", get_settings_obj)

    moderation_stub = ModuleType("fanic.moderation")
    setattr(moderation_stub, "get_explicit_threshold", get_explicit_threshold)
    setattr(moderation_stub, "moderate_image", moderate_image)
    setattr(moderation_stub, "moderate_image_bytes", moderate_image_bytes)
    setattr(moderation_stub, "suggested_rating_for_nsfw", suggested_rating_for_nsfw)

    repository_stub = ModuleType("fanic.repository")
    setattr(repository_stub, "WorkChapterRow", dict)
    setattr(repository_stub, "WorkPageRow", dict)
    setattr(repository_stub, "add_work_chapter", make_chapter)
    setattr(repository_stub, "create_work_version_snapshot", make_snapshot)
    setattr(repository_stub, "count_uploaded_pages_for_user", lambda username: 0)
    setattr(repository_stub, "delete_work_chapter", always_true)
    setattr(repository_stub, "get_work", get_work_none)
    setattr(repository_stub, "list_work_chapter_members", empty_list)
    setattr(repository_stub, "list_work_chapters", empty_list)
    setattr(repository_stub, "list_work_page_image_names", empty_list)
    setattr(repository_stub, "list_work_page_rows", empty_list)
    setattr(repository_stub, "replace_work_chapter_members", noop)
    setattr(repository_stub, "replace_work_pages", noop)
    setattr(repository_stub, "replace_work_tags", noop)
    setattr(repository_stub, "update_work_chapter", always_true)
    setattr(repository_stub, "upsert_work", noop)

    db_stub = ModuleType("fanic.db")
    setattr(db_stub, "get_connection", get_connection_none)

    utils_stub = ModuleType("fanic.utils")
    setattr(utils_stub, "slugify", slugify_value)

    monkeypatch.setitem(sys.modules, "fanic.settings", settings_stub)
    monkeypatch.setitem(sys.modules, "fanic.moderation", moderation_stub)
    monkeypatch.setitem(sys.modules, "fanic.repository", repository_stub)
    monkeypatch.setitem(sys.modules, "fanic.db", db_stub)
    monkeypatch.setitem(sys.modules, "fanic.utils", utils_stub)

    module_name = f"ingest_helpers_test_{tmp_path.name}"
    spec = importlib.util.spec_from_file_location(module_name, INGEST_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ingest module for helper tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    with BytesIO() as buffer:
        image = Image.new("RGB", size, color=(255, 0, 0))
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def test_sort_and_hash_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    names = ["page10.png", "page2.png", "page1.png"]
    sorted_names = sorted(names, key=ingest._natural_member_sort_key)
    assert sorted_names == ["page1.png", "page2.png", "page10.png"]

    rel = ingest._content_addressed_rel_path(b"abc", " .AVIF ")
    assert rel.startswith("_objects/")
    assert rel.endswith(".avif")


def test_content_addressed_storage_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    base_dir = tmp_path / "works" / "work-1" / "pages"
    base_dir.mkdir(parents=True, exist_ok=True)
    data = b"hello-world"
    rel1 = ingest._store_content_addressed(base_dir, data, "bin")
    rel2 = ingest._store_content_addressed(base_dir, data, "bin")

    assert rel1 == rel2
    assert (base_dir / rel1).read_bytes() == data


def test_quality_ramp_after_soft_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    monkeypatch.setattr(ingest, "IMAGE_AVIF_QUALITY", 75)
    monkeypatch.setattr(ingest, "USER_PAGE_SOFT_CAP", 2000)
    monkeypatch.setattr(ingest, "USER_PAGE_QUALITY_RAMP_MULTIPLIER", 1.5)

    assert ingest._quality_for_account_page(2000) == 75
    assert ingest._quality_for_account_page(2500) < 75
    assert ingest._quality_for_account_page(3000) == 1
    assert ingest._quality_for_account_page(3500) == 1


def test_small_conversion_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    assert ingest._as_int(10, 1) == 10
    assert ingest._as_int("12", 1) == 12
    assert ingest._as_int("bad", 3) == 3
    assert ingest._as_str(None, "fallback") == "fallback"
    assert ingest._as_str(123, "") == "123"
    assert ingest._comma_split(" a, b ,, c ") == ["a", "b", "c"]


def test_rating_normalization_and_elevation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    assert ingest._normalize_rating("pg-13") == "Teen And Up Audiences"
    assert ingest._normalize_rating("explicit") == "Explicit"
    assert ingest._normalize_rating(" ") == "Not Rated"

    assert ingest._elevate_rating("General Audiences", "Explicit") == "Explicit"
    assert ingest._elevate_rating("Explicit", "Teen And Up Audiences") == "Explicit"


def test_parse_comicinfo_xml_extracts_expected_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    xml_text = """
    <ComicInfo>
      <Title>My Comic</Title>
      <Summary>Summary text</Summary>
      <LanguageISO>en</LanguageISO>
      <Series>Series X</Series>
      <Number>7</Number>
      <Characters>Alice, Bob</Characters>
      <Tags>tag1, tag2</Tags>
      <AgeRating>pg-13</AgeRating>
      <Year>2026</Year>
      <Month>3</Month>
      <Day>9</Day>
    </ComicInfo>
    """
    parsed = ingest.parse_comicinfo_xml(xml_text)

    assert parsed["title"] == "My Comic"
    assert parsed["language"] == "en"
    assert parsed["fandoms"] == ["Series X"]
    assert parsed["characters"] == ["Alice", "Bob"]
    assert parsed["freeform_tags"] == ["tag1", "tag2"]
    assert parsed["rating"] == "Teen And Up Audiences"
    assert parsed["published_at"] == "2026-03-09"


def test_image_detection_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    assert ingest._is_image_member_name("page1.png") is True
    assert ingest._is_image_member_name("notes.txt") is False

    assert ingest._looks_like_image_bytes(_png_bytes()) is True
    assert ingest._looks_like_image_bytes(b"not-an-image") is False


def test_chapter_seed_members_from_range(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    page_order = ["p1", "p2", "p3", "p4"]
    chapter: object = {"start_page": 2, "end_page": 3}
    chapter_map = cast(dict[str, Any], chapter)
    seeded = ingest._chapter_seed_members_from_range(page_order, chapter_map)
    assert seeded == ["p2", "p3"]

    out_of_bounds: object = {"start_page": 10, "end_page": 20}
    out_of_bounds_map = cast(dict[str, Any], out_of_bounds)
    seeded_fallback = ingest._chapter_seed_members_from_range(
        page_order, out_of_bounds_map
    )
    assert seeded_fallback == ["p4"]


def test_ingest_cbz_success_with_override_and_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "sample.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr(
            "ComicInfo.xml",
            """
            <ComicInfo>
              <Title>Zip Title</Title>
              <AgeRating>general</AgeRating>
            </ComicInfo>
            """,
        )
        zip_file.writestr("page01.png", _png_bytes((10, 8)))

    override_path = tmp_path / "override.json"
    override_path.write_text(
        json.dumps(
            {
                "title": "Override Title",
                "id": "work123",
                "slug": "override-title",
                "rating": "General Audiences",
                "page_order": ["page01.png"],
            }
        ),
        encoding="utf-8",
    )

    def moderate_image_bytes_stub(
        data: bytes, suffix: str = ".png"
    ) -> dict[str, object]:
        _ = (data, suffix)
        return {
            "allow": True,
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.95,
            "nsfw_confidences": {"sfw": 0.05, "explicit": 0.95},
        }

    def render_image_bytes_stub(image: object, fmt: str, quality: int) -> bytes:
        _ = (image, fmt, quality)
        return b"avif-bytes"

    monkeypatch.setattr(
        ingest,
        "moderate_image_bytes",
        moderate_image_bytes_stub,
    )
    monkeypatch.setattr(ingest, "_render_image_bytes", render_image_bytes_stub)

    progress_events: list[str] = []

    def progress_hook(stage: str, message: str, current: int, total: int) -> None:
        _ = (message, current, total)
        progress_events.append(stage)

    result = ingest.ingest_cbz(
        cbz_path,
        metadata_override_path=override_path,
        uploader_username="alice",
        progress_hook=progress_hook,
    )

    assert result["work_id"] == "work123"
    assert result["slug"] == "override-title"
    assert result["page_count"] == 1
    assert result["rating_before"] == "General Audiences"
    assert result["rating_after"] == "Explicit"
    assert result["rating_auto_elevated"] is True
    assert "read-metadata" in progress_events
    assert "done" in progress_events


def test_ingest_cbz_raises_when_no_recognized_images(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "no-images.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr("ComicInfo.xml", "<ComicInfo></ComicInfo>")
        zip_file.writestr("notes.txt", "hello")

    with pytest.raises(ValueError, match="contains no recognizable image pages"):
        ingest.ingest_cbz(cbz_path)


def test_validate_zip_archive_limits_rejects_member_too_large(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "member-too-large.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr("page01.png", b"x" * 12)

    monkeypatch.setattr(ingest, "MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES", 10)
    monkeypatch.setattr(ingest, "MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES", 100)

    with ingest.ZipFile(cbz_path) as zip_file:
        with pytest.raises(ValueError, match="member exceeds maximum allowed"):
            ingest._validate_zip_archive_limits(zip_file)


def test_validate_zip_archive_limits_rejects_total_too_large(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "total-too-large.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr("page01.png", b"x" * 8)
        zip_file.writestr("page02.png", b"y" * 8)

    monkeypatch.setattr(ingest, "MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES", 100)
    monkeypatch.setattr(ingest, "MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES", 10)

    with ingest.ZipFile(cbz_path) as zip_file:
        with pytest.raises(ValueError, match="total uncompressed size"):
            ingest._validate_zip_archive_limits(zip_file)


def test_ingest_cbz_rejects_when_page_count_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "too-many-pages.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr("page01.png", _png_bytes((8, 8)))
        zip_file.writestr("page02.png", _png_bytes((8, 8)))
        zip_file.writestr("page03.png", _png_bytes((8, 8)))

    monkeypatch.setattr(ingest, "MAX_INGEST_PAGES", 2)

    with pytest.raises(ValueError, match="maximum allowed page count"):
        ingest.ingest_cbz(cbz_path)


def test_ingest_cbz_rejects_when_image_pixel_count_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    cbz_path = tmp_path / "too-many-pixels.cbz"
    with ingest.ZipFile(cbz_path, mode="w") as zip_file:
        zip_file.writestr("page01.png", _png_bytes((10, 8)))

    monkeypatch.setattr(ingest, "MAX_UPLOAD_IMAGE_PIXELS", 10)

    with pytest.raises(ValueError, match="Failed to convert page to AVIF"):
        ingest.ingest_cbz(cbz_path)


def test_ingest_editor_page_rejects_when_image_pixel_count_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(_png_bytes((10, 8)))

    monkeypatch.setattr(ingest, "MAX_UPLOAD_IMAGE_PIXELS", 10)

    with pytest.raises(ValueError, match="Failed to convert page image"):
        ingest.ingest_editor_page(image_path, {}, "alice")


def test_convert_existing_thumbs_to_avif_counters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    work_id = "w1"
    pages_dir = tmp_path / "works" / work_id / "pages"
    thumbs_dir = tmp_path / "works" / work_id / "thumbs"
    pages_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    image_name = "source.png"
    (pages_dir / image_name).write_bytes(_png_bytes((12, 12)))

    rows: list[dict[str, object]] = [
        {
            "work_id": work_id,
            "page_index": 1,
            "image_filename": image_name,
            "thumb_filename": "old-thumb.avif",
        },
        {
            "work_id": "missing",
            "page_index": 2,
            "image_filename": "missing.png",
            "thumb_filename": "missing.avif",
        },
    ]

    executed_updates: list[list[tuple[str, str, int]]] = []

    class FakeCursor:
        def __init__(self, payload: list[dict[str, object]]) -> None:
            self.payload: list[dict[str, object]] = payload

        def fetchall(self) -> list[dict[str, object]]:
            return self.payload

    class FakeConnection:
        def execute(self, _query: str) -> FakeCursor:
            return FakeCursor(rows)

        def executemany(self, _query: str, updates: list[tuple[str, str, int]]) -> None:
            executed_updates.append(updates)

    @contextmanager
    def fake_get_connection() -> Any:
        yield FakeConnection()

    def render_thumb_bytes_stub(image: object, fmt: str, quality: int) -> bytes:
        _ = (image, fmt, quality)
        return b"thumb-bytes"

    def store_content_addressed_stub(
        base_dir: Path,
        data: bytes,
        extension: str,
    ) -> str:
        _ = (base_dir, data, extension)
        return "new-thumb.avif"

    monkeypatch.setattr(ingest, "get_connection", fake_get_connection)
    monkeypatch.setattr(ingest, "_render_image_bytes", render_thumb_bytes_stub)
    monkeypatch.setattr(
        ingest, "_store_content_addressed", store_content_addressed_stub
    )

    result = ingest.convert_existing_thumbs_to_avif(dry_run=False)

    assert result["scanned"] == 2
    assert result["converted"] == 1
    assert result["missing_source"] == 1
    assert result["updated_rows"] == 1
    assert len(executed_updates) == 1
    assert executed_updates[0][0][1:] == (work_id, 1)


def test_require_editor_owner_errors_and_permission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    def get_work_missing(_work_id: str) -> None:
        return None

    def get_work_other_owner(_work_id: str) -> dict[str, object]:
        return {"uploader_username": "owner"}

    monkeypatch.setattr(ingest, "get_work", get_work_missing)
    with pytest.raises(FileNotFoundError, match="Work not found"):
        ingest._require_editor_owner("missing", "alice")

    monkeypatch.setattr(ingest, "get_work", get_work_other_owner)
    with pytest.raises(PermissionError, match="Only the original uploader"):
        ingest._require_editor_owner("w1", "alice")


def test_editor_move_page_reorders_and_snapshots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    pages: list[dict[str, object]] = [
        {
            "page_index": 1,
            "image_filename": "p1.avif",
            "thumb_filename": "t1.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 2,
            "image_filename": "p2.avif",
            "thumb_filename": "t2.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 3,
            "image_filename": "p3.avif",
            "thumb_filename": "t3.avif",
            "width": 10,
            "height": 10,
        },
    ]
    replaced_pages: list[list[dict[str, object]]] = []
    snapshots: list[dict[str, object]] = []

    def require_editor_owner_stub(work_id: str, uploader: str) -> dict[str, object]:
        _ = uploader
        return {"id": work_id}

    def list_work_page_rows_stub(_work_id: str) -> list[dict[str, object]]:
        return list(pages)

    def replace_work_pages_stub(
        _work_id: str,
        new_pages: list[dict[str, object]],
    ) -> None:
        replaced_pages.append(new_pages)

    def reconcile_stub(
        work_id: str,
        removed_image_filename: str | None = None,
    ) -> None:
        _ = (work_id, removed_image_filename)

    def upsert_existing_work_stub(
        existing_work: dict[str, object],
        page_rows: list[dict[str, object]],
    ) -> None:
        _ = (existing_work, page_rows)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "work_id": work_id,
            "action": action,
            "actor": actor,
            "details": details,
        }
        snapshots.append(payload)
        return {"version_id": "v1"}

    monkeypatch.setattr(ingest, "_require_editor_owner", require_editor_owner_stub)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_work_page_rows_stub)
    monkeypatch.setattr(ingest, "replace_work_pages", replace_work_pages_stub)
    monkeypatch.setattr(
        ingest, "_reconcile_chapters_after_page_changes", reconcile_stub
    )
    monkeypatch.setattr(ingest, "_upsert_existing_work", upsert_existing_work_stub)
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)

    result = ingest.editor_move_page("w1", 3, 1, "alice")

    assert result == {"work_id": "w1", "page_count": 3, "from": 3, "to": 1}
    assert [row["image_filename"] for row in replaced_pages[0]] == [
        "p3.avif",
        "p1.avif",
        "p2.avif",
    ]
    assert snapshots[0]["action"] == "editor-move-page"


def test_editor_reorder_gallery_validates_and_updates_chapters(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    base_pages: list[dict[str, object]] = [
        {
            "page_index": 1,
            "image_filename": "a.avif",
            "thumb_filename": "ta.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 2,
            "image_filename": "b.avif",
            "thumb_filename": "tb.avif",
            "width": 10,
            "height": 10,
        },
    ]
    chapter_rows: list[dict[str, object]] = [
        {"id": 7, "title": "Ch1", "start_page": 1, "end_page": 2}
    ]
    chapter_members_updates: list[list[str]] = []

    def require_editor_owner_stub(
        work_id: str,
        uploader: str,
    ) -> dict[str, object]:
        _ = uploader
        return {"id": work_id}

    def list_work_page_rows_stub(_work_id: str) -> list[dict[str, object]]:
        return list(base_pages)

    def list_work_chapters_stub(_work_id: str) -> list[dict[str, object]]:
        return list(chapter_rows)

    def list_work_page_image_names_stub(_work_id: str) -> list[str]:
        return ["b.avif", "a.avif"]

    def list_work_chapter_members_stub(_chapter_id: int) -> list[str]:
        return ["a.avif", "b.avif"]

    def replace_work_pages_stub(
        _work_id: str,
        page_rows: list[dict[str, object]],
    ) -> None:
        _ = page_rows

    def update_work_chapter_stub(
        work_id: str,
        chapter_id: int,
        title: str,
        start_page: int,
        end_page: int,
    ) -> bool:
        _ = (work_id, chapter_id, title, start_page, end_page)
        return True

    def replace_work_chapter_members_stub(
        chapter_id: int,
        members: list[str],
    ) -> None:
        _ = chapter_id
        chapter_members_updates.append(members)

    def delete_work_chapter_stub(work_id: str, chapter_id: int) -> bool:
        _ = (work_id, chapter_id)
        return True

    def upsert_existing_work_stub(
        existing_work: dict[str, object],
        page_rows: list[dict[str, object]],
    ) -> None:
        _ = (existing_work, page_rows)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        _ = (work_id, action, actor, details)
        return {"version_id": "v1"}

    monkeypatch.setattr(ingest, "_require_editor_owner", require_editor_owner_stub)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_work_page_rows_stub)
    monkeypatch.setattr(ingest, "list_work_chapters", list_work_chapters_stub)
    monkeypatch.setattr(
        ingest,
        "list_work_page_image_names",
        list_work_page_image_names_stub,
    )
    monkeypatch.setattr(
        ingest,
        "list_work_chapter_members",
        list_work_chapter_members_stub,
    )
    monkeypatch.setattr(ingest, "replace_work_pages", replace_work_pages_stub)
    monkeypatch.setattr(ingest, "update_work_chapter", update_work_chapter_stub)
    monkeypatch.setattr(
        ingest,
        "replace_work_chapter_members",
        replace_work_chapter_members_stub,
    )
    monkeypatch.setattr(ingest, "delete_work_chapter", delete_work_chapter_stub)
    monkeypatch.setattr(ingest, "_upsert_existing_work", upsert_existing_work_stub)
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)

    with pytest.raises(
        ValueError, match="Ordered page list does not match existing pages"
    ):
        ingest.editor_reorder_gallery("w1", ["a.avif"], {}, "alice")

    result = ingest.editor_reorder_gallery(
        "w1",
        ["b.avif", "a.avif"],
        {"7": ["a.avif"]},
        "alice",
    )

    assert result == {"work_id": "w1", "page_count": 2}
    assert chapter_members_updates[-1] == ["a.avif"]


def test_editor_update_and_delete_chapter_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    def require_editor_owner_stub(work_id: str, uploader: str) -> dict[str, object]:
        _ = uploader
        return {"id": work_id}

    def list_work_page_rows_stub(_work_id: str) -> list[dict[str, object]]:
        return [{"page_index": 1}, {"page_index": 2}]

    def update_chapter_false_stub(
        work_id: str,
        chapter_id: int,
        title: str,
        start_page: int,
        end_page: int,
    ) -> bool:
        _ = (work_id, chapter_id, title, start_page, end_page)
        return False

    def update_chapter_true_stub(
        work_id: str,
        chapter_id: int,
        title: str,
        start_page: int,
        end_page: int,
    ) -> bool:
        _ = (work_id, chapter_id, title, start_page, end_page)
        return True

    def list_work_page_image_names_stub(_work_id: str) -> list[str]:
        return ["p1", "p2"]

    def replace_chapter_members_stub(chapter_id: int, members: list[str]) -> None:
        _ = chapter_id
        captured_members.append(members)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        _ = (work_id, action, actor, details)
        return {"version_id": "v1"}

    def delete_chapter_false_stub(work_id: str, chapter_id: int) -> bool:
        _ = (work_id, chapter_id)
        return False

    def delete_chapter_true_stub(work_id: str, chapter_id: int) -> bool:
        _ = (work_id, chapter_id)
        return True

    monkeypatch.setattr(ingest, "_require_editor_owner", require_editor_owner_stub)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_work_page_rows_stub)

    with pytest.raises(ValueError, match="Chapter range is invalid"):
        ingest.editor_update_chapter("w1", 1, "Ch", 0, 2, "alice")

    monkeypatch.setattr(ingest, "update_work_chapter", update_chapter_false_stub)
    assert ingest.editor_update_chapter("w1", 1, "Ch", 1, 2, "alice") is False

    captured_members: list[list[str]] = []
    monkeypatch.setattr(ingest, "update_work_chapter", update_chapter_true_stub)
    monkeypatch.setattr(
        ingest,
        "list_work_page_image_names",
        list_work_page_image_names_stub,
    )
    monkeypatch.setattr(
        ingest,
        "replace_work_chapter_members",
        replace_chapter_members_stub,
    )
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)
    assert ingest.editor_update_chapter("w1", 1, "Ch", 1, 2, "alice") is True
    assert captured_members[-1] == ["p1", "p2"]

    monkeypatch.setattr(ingest, "delete_work_chapter", delete_chapter_false_stub)
    assert ingest.editor_delete_chapter("w1", 1, "alice") is False

    monkeypatch.setattr(ingest, "delete_work_chapter", delete_chapter_true_stub)
    assert ingest.editor_delete_chapter("w1", 1, "alice") is True


def test_ingest_editor_page_missing_image_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    missing_image = tmp_path / "does-not-exist.png"
    with pytest.raises(FileNotFoundError, match="Image not found"):
        ingest.ingest_editor_page(missing_image, {}, "alice")


def test_ingest_editor_page_rejects_missing_work_and_owner_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(_png_bytes((16, 16)))

    def get_work_missing(_work_id: str | None) -> None:
        return None

    monkeypatch.setattr(ingest, "get_work", get_work_missing)
    with pytest.raises(FileNotFoundError, match="Work not found"):
        ingest.ingest_editor_page(image_path, {}, "alice", work_id="w1")

    def get_work_other_owner(_work_id: str | None) -> dict[str, object]:
        return {"uploader_username": "bob"}

    monkeypatch.setattr(ingest, "get_work", get_work_other_owner)
    with pytest.raises(PermissionError, match="Only the original uploader"):
        ingest.ingest_editor_page(image_path, {}, "alice", work_id="w1")


def test_ingest_editor_page_blocks_when_moderation_disallows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(_png_bytes((16, 16)))

    def moderate_image_blocked(path: str) -> dict[str, object]:
        _ = path
        return {
            "allow": False,
            "reasons": ["nsfw"],
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.99,
            "nsfw_confidences": {"sfw": 0.01, "explicit": 0.99},
        }

    monkeypatch.setattr(ingest, "moderate_image", moderate_image_blocked)

    with pytest.raises(ingest.ModerationBlockedError):
        ingest.ingest_editor_page(image_path, {}, "alice")


def test_ingest_editor_page_existing_work_inserts_and_reconciles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)
    (tmp_path / "cbz").mkdir(parents=True, exist_ok=True)

    image_path = tmp_path / "page.png"
    image_path.write_bytes(_png_bytes((32, 20)))

    existing_pages: list[dict[str, object]] = [
        {
            "page_index": 1,
            "image_filename": "old-1.avif",
            "thumb_filename": "old-t1.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 2,
            "image_filename": "old-2.avif",
            "thumb_filename": "old-t2.avif",
            "width": 10,
            "height": 10,
        },
    ]
    existing_work: dict[str, object] = {
        "id": "w1",
        "slug": "existing-slug",
        "title": "Existing Title",
        "summary": "Existing summary",
        "rating": "General Audiences",
        "warnings": "No Archive Warnings Apply",
        "language": "en",
        "status": "complete",
        "creators": ["c1"],
        "series_name": "Series A",
        "series_index": "2",
        "published_at": "2026-01-02",
        "cover_page_index": "3",
        "cbz_path": "",
        "uploader_username": "alice",
    }

    replaced_pages: list[list[dict[str, object]]] = []
    upsert_payloads: list[dict[str, object]] = []
    reconciled: list[str] = []
    snapshots: list[dict[str, object]] = []

    def get_work_existing(_work_id: str | None) -> dict[str, object]:
        return dict(existing_work)

    def moderate_image_explicit(path: str) -> dict[str, object]:
        _ = path
        return {
            "allow": True,
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.95,
            "nsfw_confidences": {"sfw": 0.05, "explicit": 0.95},
        }

    def list_pages_stub(_work_id: str) -> list[dict[str, object]]:
        return list(existing_pages)

    def render_image_bytes_stub(image: object, fmt: str, quality: int) -> bytes:
        _ = (image, fmt, quality)
        return b"encoded"

    def store_page_stub(base_dir: Path, data: bytes, extension: str) -> str:
        _ = (base_dir, data, extension)
        if extension == "avif" and len(replaced_pages) == 0:
            return "new-page.avif"
        return "new-thumb.avif"

    def upsert_work_stub(work: dict[str, object]) -> None:
        upsert_payloads.append(work)

    def replace_work_pages_stub(work_id: str, pages: list[dict[str, object]]) -> None:
        _ = work_id
        replaced_pages.append(pages)

    def reconcile_stub(work_id: str, removed_image_filename: str | None = None) -> None:
        _ = removed_image_filename
        reconciled.append(work_id)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "work_id": work_id,
            "action": action,
            "actor": actor,
            "details": details,
        }
        snapshots.append(payload)
        return {"version_id": "v1"}

    monkeypatch.setattr(ingest, "get_work", get_work_existing)
    monkeypatch.setattr(ingest, "moderate_image", moderate_image_explicit)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_pages_stub)
    monkeypatch.setattr(ingest, "_render_image_bytes", render_image_bytes_stub)
    monkeypatch.setattr(ingest, "_store_content_addressed", store_page_stub)
    monkeypatch.setattr(ingest, "upsert_work", upsert_work_stub)
    monkeypatch.setattr(ingest, "replace_work_pages", replace_work_pages_stub)
    monkeypatch.setattr(
        ingest,
        "_reconcile_chapters_after_page_changes",
        reconcile_stub,
    )
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)

    result = ingest.ingest_editor_page(
        image_path,
        {"status": "unexpected-status"},
        "alice",
        work_id="w1",
        insert_after_page_index=1,
    )

    assert result["work_id"] == "w1"
    assert result["latest_page_index"] == 2
    assert result["rating_before"] == "General Audiences"
    assert result["rating_after"] == "Explicit"
    assert result["rating_auto_elevated"] is True
    assert result["page_count"] == 3

    assert len(replaced_pages) == 1
    assert [page["image_filename"] for page in replaced_pages[0]] == [
        "old-1.avif",
        "new-page.avif",
        "old-2.avif",
    ]

    assert upsert_payloads[0]["status"] == "in_progress"
    assert upsert_payloads[0]["cover_page_index"] == 3
    assert str(upsert_payloads[0]["cbz_path"]).endswith("w1.cbz")
    assert reconciled == ["w1"]
    assert snapshots[0]["action"] == "editor-add-page"


def test_reconcile_chapters_updates_and_deletes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    updated_calls: list[dict[str, object]] = []
    deleted_calls: list[int] = []
    replaced_member_calls: list[tuple[int, list[str]]] = []

    chapters: list[dict[str, object]] = [
        {"id": 1, "title": "Keep", "start_page": 1, "end_page": 3},
        {"id": 2, "title": "Drop", "start_page": 1, "end_page": 1},
    ]

    def list_page_order_stub(_work_id: str) -> list[str]:
        return ["a", "b", "c"]

    def list_chapters_stub(_work_id: str) -> list[dict[str, object]]:
        return list(chapters)

    def list_members_stub(chapter_id: int) -> list[str]:
        if chapter_id == 1:
            return ["a", "missing", "b"]
        return ["removed"]

    def delete_chapter_stub(work_id: str, chapter_id: int) -> bool:
        _ = work_id
        deleted_calls.append(chapter_id)
        return True

    def update_chapter_stub(
        work_id: str,
        chapter_id: int,
        title: str,
        start_page: int,
        end_page: int,
    ) -> bool:
        _ = work_id
        updated_calls.append(
            {
                "chapter_id": chapter_id,
                "title": title,
                "start_page": start_page,
                "end_page": end_page,
            }
        )
        return True

    def replace_members_stub(chapter_id: int, members: list[str]) -> None:
        replaced_member_calls.append((chapter_id, members))

    monkeypatch.setattr(ingest, "list_work_page_image_names", list_page_order_stub)
    monkeypatch.setattr(ingest, "list_work_chapters", list_chapters_stub)
    monkeypatch.setattr(ingest, "list_work_chapter_members", list_members_stub)
    monkeypatch.setattr(ingest, "delete_work_chapter", delete_chapter_stub)
    monkeypatch.setattr(ingest, "update_work_chapter", update_chapter_stub)
    monkeypatch.setattr(
        ingest,
        "replace_work_chapter_members",
        replace_members_stub,
    )

    ingest._reconcile_chapters_after_page_changes(
        "w1", removed_image_filename="removed"
    )

    assert updated_calls[0]["chapter_id"] == 1
    assert updated_calls[0]["start_page"] == 1
    assert updated_calls[0]["end_page"] == 2
    assert replaced_member_calls[0] == (1, ["a", "b"])
    assert deleted_calls == [2]


def test_editor_replace_page_image_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    missing_path = tmp_path / "missing.png"
    with pytest.raises(FileNotFoundError, match="Image not found"):
        ingest.editor_replace_page_image(missing_path, "w1", 1, "alice")

    image_path = tmp_path / "replace.png"
    image_path.write_bytes(_png_bytes((20, 12)))

    def moderate_blocked(_path: str) -> dict[str, object]:
        return {
            "allow": False,
            "reasons": ["nsfw"],
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 1.0,
            "nsfw_confidences": {"sfw": 0.0, "explicit": 1.0},
        }

    monkeypatch.setattr(ingest, "moderate_image", moderate_blocked)
    with pytest.raises(ingest.ModerationBlockedError):
        ingest.editor_replace_page_image(image_path, "w1", 1, "alice")

    pages: list[dict[str, object]] = [
        {
            "page_index": 1,
            "image_filename": "old-page.avif",
            "thumb_filename": "old-thumb.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 2,
            "image_filename": "other.avif",
            "thumb_filename": "other-thumb.avif",
            "width": 10,
            "height": 10,
        },
    ]
    replaced_pages: list[list[dict[str, object]]] = []
    replaced_members: list[tuple[int, list[str]]] = []
    snapshots: list[dict[str, object]] = []
    existing_work: dict[str, object] = {"rating": "General Audiences"}

    def moderate_allow(_path: str) -> dict[str, object]:
        return {
            "allow": True,
            "style": "comic",
            "style_confidences": {"comic": 1.0},
            "nsfw_score": 0.95,
            "nsfw_confidences": {"sfw": 0.05, "explicit": 0.95},
        }

    def require_owner_stub(work_id: str, uploader: str) -> dict[str, object]:
        _ = (work_id, uploader)
        return existing_work

    def list_pages_stub(_work_id: str) -> list[dict[str, object]]:
        return list(pages)

    def render_image_bytes_stub(image: object, fmt: str, quality: int) -> bytes:
        _ = (image, fmt, quality)
        return b"encoded"

    call_count = {"count": 0}

    def store_stub(base_dir: Path, data: bytes, extension: str) -> str:
        _ = (base_dir, data, extension)
        call_count["count"] += 1
        if call_count["count"] == 1:
            return "new-page.avif"
        return "new-thumb.avif"

    def replace_pages_stub(work_id: str, new_pages: list[dict[str, object]]) -> None:
        _ = work_id
        replaced_pages.append(new_pages)

    def list_chapters_stub(_work_id: str) -> list[dict[str, object]]:
        return [{"id": 7, "title": "Ch"}]

    def list_members_stub(_chapter_id: int) -> list[str]:
        return ["old-page.avif", "other.avif"]

    def replace_members_stub(chapter_id: int, members: list[str]) -> None:
        replaced_members.append((chapter_id, members))

    def reconcile_stub(work_id: str, removed_image_filename: str | None = None) -> None:
        _ = (work_id, removed_image_filename)

    def upsert_existing_work_stub(
        existing: dict[str, object],
        new_pages: list[dict[str, object]],
    ) -> None:
        _ = (existing, new_pages)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "work_id": work_id,
            "action": action,
            "actor": actor,
            "details": details,
        }
        snapshots.append(payload)
        return {"version_id": "v1"}

    monkeypatch.setattr(ingest, "moderate_image", moderate_allow)
    monkeypatch.setattr(ingest, "_require_editor_owner", require_owner_stub)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_pages_stub)
    monkeypatch.setattr(ingest, "_render_image_bytes", render_image_bytes_stub)
    monkeypatch.setattr(ingest, "_store_content_addressed", store_stub)
    monkeypatch.setattr(ingest, "replace_work_pages", replace_pages_stub)
    monkeypatch.setattr(ingest, "list_work_chapters", list_chapters_stub)
    monkeypatch.setattr(ingest, "list_work_chapter_members", list_members_stub)
    monkeypatch.setattr(ingest, "replace_work_chapter_members", replace_members_stub)
    monkeypatch.setattr(
        ingest,
        "_reconcile_chapters_after_page_changes",
        reconcile_stub,
    )
    monkeypatch.setattr(ingest, "_upsert_existing_work", upsert_existing_work_stub)
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)

    with pytest.raises(FileNotFoundError, match="Page index not found"):
        ingest.editor_replace_page_image(image_path, "w1", 99, "alice")

    result = ingest.editor_replace_page_image(image_path, "w1", 1, "alice")
    assert result["work_id"] == "w1"
    assert result["replaced_page_index"] == 1
    assert result["rating_before"] == "General Audiences"
    assert result["rating_after"] == "Explicit"
    assert result["rating_auto_elevated"] is True
    assert replaced_pages[0][0]["image_filename"] == "new-page.avif"
    assert replaced_members[0] == (7, ["new-page.avif", "other.avif"])
    assert snapshots[0]["action"] == "editor-replace-page"


def test_editor_delete_page_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ingest = _load_ingest_with_stubs(monkeypatch, tmp_path)

    pages: list[dict[str, object]] = [
        {
            "page_index": 1,
            "image_filename": "a.avif",
            "thumb_filename": "ta.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 2,
            "image_filename": "b.avif",
            "thumb_filename": "tb.avif",
            "width": 10,
            "height": 10,
        },
        {
            "page_index": 3,
            "image_filename": "c.avif",
            "thumb_filename": "tc.avif",
            "width": 10,
            "height": 10,
        },
    ]

    reconciled: list[tuple[str, str | None]] = []
    replaced: list[list[dict[str, object]]] = []
    snapshots: list[dict[str, object]] = []

    def require_owner_stub(work_id: str, uploader: str) -> dict[str, object]:
        _ = (work_id, uploader)
        return {"id": work_id}

    def list_pages_stub(_work_id: str) -> list[dict[str, object]]:
        return list(pages)

    def replace_pages_stub(work_id: str, new_pages: list[dict[str, object]]) -> None:
        _ = work_id
        replaced.append(new_pages)

    def reconcile_stub(work_id: str, removed_image_filename: str | None = None) -> None:
        reconciled.append((work_id, removed_image_filename))

    def upsert_existing_work_stub(
        existing: dict[str, object],
        new_pages: list[dict[str, object]],
    ) -> None:
        _ = (existing, new_pages)

    def snapshot_stub(
        work_id: str,
        action: str,
        actor: str | None,
        details: dict[str, object],
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "work_id": work_id,
            "action": action,
            "actor": actor,
            "details": details,
        }
        snapshots.append(payload)
        return {"version_id": "v1"}

    monkeypatch.setattr(ingest, "_require_editor_owner", require_owner_stub)
    monkeypatch.setattr(ingest, "list_work_page_rows", list_pages_stub)
    monkeypatch.setattr(ingest, "replace_work_pages", replace_pages_stub)
    monkeypatch.setattr(
        ingest,
        "_reconcile_chapters_after_page_changes",
        reconcile_stub,
    )
    monkeypatch.setattr(ingest, "_upsert_existing_work", upsert_existing_work_stub)
    monkeypatch.setattr(ingest, "create_work_version_snapshot", snapshot_stub)

    with pytest.raises(FileNotFoundError, match="Page index not found"):
        ingest.editor_delete_page("w1", 99, "alice")

    result = ingest.editor_delete_page("w1", 2, "alice")
    assert result == {"work_id": "w1", "page_count": 2, "deleted_page_index": 2}
    assert [page["page_index"] for page in replaced[0]] == [1, 2]
    assert [page["image_filename"] for page in replaced[0]] == ["a.avif", "c.avif"]
    assert reconciled[0] == ("w1", "b.avif")
    assert snapshots[0]["action"] == "editor-delete-page"
