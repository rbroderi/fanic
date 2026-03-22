from __future__ import annotations

import importlib.util
import sys
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
    def noop() -> None:
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

    base_dir = tmp_path / "objects"
    data = b"hello-world"
    rel1 = ingest._store_content_addressed(base_dir, data, "bin")
    rel2 = ingest._store_content_addressed(base_dir, data, "bin")

    assert rel1 == rel2
    assert (base_dir / rel1).read_bytes() == data


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
