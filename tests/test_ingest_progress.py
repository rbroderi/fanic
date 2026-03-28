import pytest

import fanic.ingest_progress as ingest_progress


def test_set_and_get_progress_round_trip() -> None:
    ingest_progress.set_progress(
        "tok-1",
        stage="ingesting",
        message="Reading archive",
        current=2,
        total=10,
        done=False,
        ok=False,
    )

    value = ingest_progress.get_progress("tok-1")

    assert value is not None
    assert value["stage"] == "ingesting"
    assert value["message"] == "Reading archive"
    assert value["current"] == 2
    assert value["total"] == 10
    assert value["done"] is False
    assert value["ok"] is False


def test_get_progress_returns_copy_not_reference() -> None:
    ingest_progress.set_progress(
        "tok-2",
        stage="extracting",
        message="Working",
        current=1,
        total=3,
    )

    value = ingest_progress.get_progress("tok-2")
    assert value is not None
    value["message"] = "mutated"

    fresh = ingest_progress.get_progress("tok-2")
    assert fresh is not None
    assert fresh["message"] == "Working"


def test_empty_token_is_ignored() -> None:
    ingest_progress.set_progress(
        "",
        stage="ingesting",
        message="should be ignored",
        current=1,
        total=1,
    )

    assert ingest_progress.get_progress("") is None
    assert ingest_progress.get_progress("missing") is None


def test_prune_stale_entries_on_set(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000.0
    monkeypatch.setattr("fanic.ingest_progress.time.time", lambda: now)

    ingest_progress.set_progress(
        "stale-token",
        stage="old",
        message="old",
        current=0,
        total=0,
    )

    now = 2_100.0
    monkeypatch.setattr("fanic.ingest_progress.time.time", lambda: now)

    ingest_progress.set_progress(
        "fresh-token",
        stage="new",
        message="new",
        current=1,
        total=2,
    )

    assert ingest_progress.get_progress("stale-token") is None
    assert ingest_progress.get_progress("fresh-token") is not None


def test_prune_stale_entries_on_get(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 3_000.0
    monkeypatch.setattr("fanic.ingest_progress.time.time", lambda: now)

    ingest_progress.set_progress(
        "stale-token",
        stage="old",
        message="old",
        current=0,
        total=0,
    )

    now = 3_500.0
    monkeypatch.setattr("fanic.ingest_progress.time.time", lambda: now)

    ingest_progress.set_progress(
        "live-token",
        stage="new",
        message="new",
        current=1,
        total=1,
        done=True,
        ok=True,
    )

    now = 4_001.0
    monkeypatch.setattr("fanic.ingest_progress.time.time", lambda: now)

    stale_value = ingest_progress.get_progress("stale-token")
    live_value = ingest_progress.get_progress("live-token")

    assert stale_value is None
    assert live_value is not None
    assert live_value["ok"] is True
