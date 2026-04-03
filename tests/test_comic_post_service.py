from fanic.cylinder_sites.fanicsite.comic_post_service import build_metadata_from_form
from fanic.cylinder_sites.fanicsite.comic_post_service import csv_values
from fanic.cylinder_sites.fanicsite.comic_post_service import parse_series_index
from fanic.cylinder_sites.fanicsite.comic_post_service import (
    should_lock_explicit_demotion,
)


def test_csv_values_and_series_index_parsing() -> None:
    assert csv_values("a, b ,, c") == ["a", "b", "c"]
    assert parse_series_index(" 2 ") == 2
    assert parse_series_index("bad") is None
    assert parse_series_index("") is None


def test_build_metadata_from_form_defaults_and_lists() -> None:
    metadata = build_metadata_from_form(
        existing_title="Existing",
        title_raw="",
        summary_raw=" summary ",
        rating_raw="",
        warnings_raw="warn1, warn2",
        status_raw="invalid",
        language_raw="",
        series_raw=" Series Name ",
        series_index_raw="x",
        published_at_raw=" 2026-04-03 ",
        fandoms_raw="f1,f2",
        relationships_raw="r1",
        characters_raw="c1,c2",
        freeform_tags_raw="t1",
    )

    assert metadata["title"] == "Existing"
    assert metadata["summary"] == "summary"
    assert metadata["rating"] == "Not Rated"
    assert metadata["warnings"] == ["warn1", "warn2"]
    assert metadata["status"] == "in_progress"
    assert metadata["language"] == "en"
    assert metadata["series"] == "Series Name"
    assert metadata["series_index"] is None
    assert metadata["published_at"] == "2026-04-03"
    assert metadata["fandoms"] == ["f1", "f2"]


def test_should_lock_explicit_demotion_logic() -> None:
    assert (
        should_lock_explicit_demotion(
            is_admin=False,
            current_rating="Explicit",
            requested_rating="Mature",
        )
        is True
    )
    assert (
        should_lock_explicit_demotion(
            is_admin=True,
            current_rating="Explicit",
            requested_rating="Mature",
        )
        is False
    )
    assert (
        should_lock_explicit_demotion(
            is_admin=False,
            current_rating="Mature",
            requested_rating="General Audiences",
        )
        is False
    )
