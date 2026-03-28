from collections.abc import Callable
from types import ModuleType


def test_build_comicinfo_xml_includes_extended_fanic_metadata(
    load_route_module: Callable[[str, str], ModuleType],
) -> None:
    module = load_route_module(
        "src/fanic/cylinder_sites/fanicsite/api/works.ex.get.py",
        "fanicsite_api_works_ex_get_comicinfo_export_test",
    )

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
