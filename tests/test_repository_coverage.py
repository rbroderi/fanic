# pyright: reportPrivateLocalImportUsage=false

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from types import TracebackType
from typing import Literal
from typing import cast
from typing import override
from uuid import UUID

import pytest


class _ManagedTestConnection(sqlite3.Connection):
    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()
        return False


def _ensure_test_runtime_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            username TEXT PRIMARY KEY,
            view_mature_rated INTEGER NOT NULL DEFAULT 0,
            view_explicit_rated INTEGER NOT NULL DEFAULT 0,
            custom_theme_enabled INTEGER NOT NULL DEFAULT 0,
            custom_theme_toml TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(user_preferences)").fetchall()}
    if "custom_theme_enabled" not in columns:
        connection.execute("ALTER TABLE user_preferences ADD COLUMN custom_theme_enabled INTEGER NOT NULL DEFAULT 0")
    if "custom_theme_toml" not in columns:
        connection.execute("ALTER TABLE user_preferences ADD COLUMN custom_theme_toml TEXT")


def _init_repository_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ModuleType:
    import fanic.db as db_module
    import fanic.repository.fanart as repository_fanart
    import fanic.repository.social as repository_social
    import fanic.repository.tags as repository_tags
    import fanic.repository.users as repository_users
    import fanic.repository.works as repository_works

    repository = ModuleType("repository_api")
    for module in (
        repository_users,
        repository_works,
        repository_tags,
        repository_fanart,
        repository_social,
    ):
        for symbol, value in vars(module).items():
            if symbol.startswith("_"):
                continue
            setattr(repository, symbol, value)

    # Keep access to one private helper used in these tests.
    setattr(repository, "_ensure_tag", repository_works._ensure_tag)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    setattr(
        repository,
        "_modules",
        SimpleNamespace(users=repository_users, works=repository_works),
    )

    schema_path = Path(__file__).resolve().parents[1] / "src" / "fanic" / "sql" / "schema.sql"
    db_path = tmp_path / "repo.sqlite3"
    with sqlite3.connect(db_path, factory=_ManagedTestConnection) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _ensure_test_runtime_schema(connection)
        db_module._ensure_runtime_schema(connection)  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=_ManagedTestConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        _ensure_test_runtime_schema(connection)
        return connection

    works_dir = tmp_path / "works"
    cbz_dir = tmp_path / "cbz"
    fanart_dir = tmp_path / "fanart"
    works_dir.mkdir(parents=True, exist_ok=True)
    cbz_dir.mkdir(parents=True, exist_ok=True)
    fanart_dir.mkdir(parents=True, exist_ok=True)
    (fanart_dir / "images").mkdir(parents=True, exist_ok=True)
    (fanart_dir / "thumbs").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(repository_users, "get_connection", get_test_connection)
    monkeypatch.setattr(repository_works, "get_connection", get_test_connection)
    monkeypatch.setattr(repository_tags, "get_connection", get_test_connection)
    monkeypatch.setattr(repository_fanart, "get_connection", get_test_connection)
    monkeypatch.setattr(repository_social, "get_connection", get_test_connection)

    monkeypatch.setattr(repository_works, "WORKS_DIR", works_dir)
    monkeypatch.setattr(repository_works, "CBZ_DIR", cbz_dir)
    monkeypatch.setattr(repository_fanart, "FANART_DIR", fanart_dir)

    setattr(repository, "get_connection", get_test_connection)
    setattr(repository, "WORKS_DIR", works_dir)
    setattr(repository, "CBZ_DIR", cbz_dir)
    setattr(repository, "FANART_DIR", fanart_dir)
    setattr(repository, "get_settings", repository_users.get_settings)
    return repository


def _seed_work(repository: ModuleType, *, work_id: str = "work-1") -> dict[str, object]:
    work: dict[str, object] = {
        "id": work_id,
        "slug": work_id,
        "title": "Test Work",
        "summary": "Summary",
        "rating": "General Audiences",
        "warnings": ["No Archive Warnings Apply"],
        "language": "en",
        "status": "in_progress",
        "creators": ["alice"],
        "series": "Series A",
        "series_index": 1,
        "published_at": "2026-03-22",
        "cover_page_index": 1,
        "page_count": 2,
        "cbz_path": str(repository.CBZ_DIR / f"{work_id}.cbz"),
        "uploader_username": "alice",
    }
    repository.upsert_work(work)
    return work


def _is_fandom_tag(tag: object) -> bool:
    if not isinstance(tag, Mapping):
        return False
    tag_map = cast(Mapping[str, object], tag)
    return str(tag_map.get("type", "")) == "fandom"


def test_user_preferences_and_theme_preference_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    assert repository.user_prefers_explicit(None) is False
    assert repository.user_prefers_explicit("alice") is False
    assert repository.user_prefers_mature(None) is False
    assert repository.user_prefers_mature("alice") is False

    repository.set_user_prefers_mature("alice", True)
    assert repository.user_prefers_mature("alice") is True
    repository.set_user_prefers_explicit("alice", True)
    assert repository.user_prefers_explicit("alice") is True

    default_theme = repository.get_user_theme_preference("alice")
    assert default_theme["enabled"] is False
    assert default_theme["toml_text"] == ""

    repository.set_user_theme_preference(
        "alice",
        enabled=True,
        toml_text='[dark]\naccent = "#b58900"\n',
    )
    enabled_theme = repository.get_user_theme_preference("alice")
    assert enabled_theme["enabled"] is True
    assert "accent" in enabled_theme["toml_text"]

    repository.set_user_theme_preference("alice", enabled=False, toml_text=None)
    retained_theme = repository.get_user_theme_preference("alice")
    assert retained_theme["enabled"] is False
    assert "accent" in retained_theme["toml_text"]

    explicit_work = {"rating": "Explicit"}
    mature_work = {"rating": "Mature"}
    assert repository.can_view_work("alice", explicit_work) is True
    assert repository.can_view_work("alice", mature_work) is True
    repository.set_user_prefers_mature("alice", False)
    assert repository.can_view_work("alice", mature_work) is False
    repository.set_user_prefers_explicit("alice", False)
    assert repository.can_view_work("alice", explicit_work) is False


def test_get_or_create_user_for_auth0_identity_creates_new_user_and_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    class _Settings:
        auth0_superadmin_email: str = "admin@fanic.media"

    monkeypatch.setattr(repository._modules.users, "get_settings", lambda: _Settings())

    username = repository.get_or_create_user_for_auth0_identity(
        subject="auth0|abc123",
        email="person@example.com",
        email_verified=True,
        display_name="Person Example",
    )

    assert str(UUID(username)) == username

    local_user = repository.get_local_user(username)
    assert local_user is not None
    assert local_user["role"] == "user"
    assert local_user["email"] == "person@example.com"

    identity = repository.get_auth_identity("auth0", "auth0|abc123")
    assert identity is not None
    assert identity["username"] == username
    assert identity["email_verified"] is True


def test_get_or_create_user_for_auth0_identity_promotes_superadmin_email(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    class _Settings:
        auth0_superadmin_email: str = "admin@fanic.media"

    monkeypatch.setattr(repository._modules.users, "get_settings", lambda: _Settings())

    first_username = repository.get_or_create_user_for_auth0_identity(
        subject="auth0|super-1",
        email="admin@fanic.media",
        email_verified=True,
        display_name="Primary Admin",
    )
    assert str(UUID(first_username)) == first_username

    local_user = repository.get_local_user(first_username)
    assert local_user is not None
    assert local_user["role"] == "superadmin"

    repeated_username = repository.get_or_create_user_for_auth0_identity(
        subject="auth0|super-1",
        email="admin@fanic.media",
        email_verified=True,
        display_name="Primary Admin Updated",
    )
    assert repeated_username == first_username


def test_get_or_create_user_for_auth0_identity_preserves_onboarding_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    class _Settings:
        auth0_superadmin_email: str = "admin@fanic.media"

    monkeypatch.setattr(repository._modules.users, "get_settings", lambda: _Settings())

    username = repository.get_or_create_user_for_auth0_identity(
        subject="auth0|preserve-1",
        email="person@example.com",
        email_verified=True,
        display_name="PersonOne",
    )
    assert str(UUID(username)) == username

    saved = repository.update_user_onboarding(
        username,
        display_name="PersonCustom",
        is_over_18=True,
    )
    assert saved is True

    repeated_username = repository.get_or_create_user_for_auth0_identity(
        subject="auth0|preserve-1",
        email="person@example.com",
        email_verified=True,
        display_name="AuthProviderName",
    )
    assert repeated_username == username

    local_user = repository.get_local_user(username)
    assert local_user is not None
    assert local_user["display_name"] == "PersonCustom"
    assert local_user["is_over_18"] is True
    assert local_user["age_gate_completed"] is True


def test_update_user_onboarding_only_applies_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    repository.create_user(
        "alice",
        display_name="AliceStart",
        email="alice@example.com",
        is_over_18=None,
        age_gate_completed=False,
    )

    first_saved = repository.update_user_onboarding(
        "alice",
        display_name="AliceOnce",
        is_over_18=True,
    )
    second_saved = repository.update_user_onboarding(
        "alice",
        display_name="AliceTwice",
        is_over_18=False,
    )

    assert first_saved is True
    assert second_saved is False

    user_row = repository.get_local_user("alice")
    assert user_row is not None
    assert user_row["display_name"] == "AliceOnce"
    assert user_row["is_over_18"] is True
    assert user_row["age_gate_completed"] is True


def test_update_user_onboarding_allows_recovery_when_age_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    repository.create_user(
        "alice",
        display_name="AliceStart",
        email="alice@example.com",
        is_over_18=None,
        age_gate_completed=True,
    )

    recovered = repository.update_user_onboarding(
        "alice",
        display_name="AliceRecovered",
        is_over_18=False,
    )

    assert recovered is True
    user_row = repository.get_local_user("alice")
    assert user_row is not None
    assert user_row["display_name"] == "AliceRecovered"
    assert user_row["is_over_18"] is False
    assert user_row["age_gate_completed"] is True


def test_work_crud_tags_pages_comments_kudos_and_versions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)
    _seed_work(repository)

    repository.replace_work_pages(
        "work-1",
        [
            {
                "page_index": 1,
                "image_filename": "p1.jpg",
                "thumb_filename": "t1.jpg",
                "width": 1000,
                "height": 1500,
            },
            {
                "page_index": 2,
                "image_filename": "p2.jpg",
                "thumb_filename": None,
                "width": 1000,
                "height": 1500,
            },
        ],
    )

    repository.update_work_metadata(
        "work-1",
        {
            "title": "Updated Title",
            "summary": "Updated Summary",
            "rating": "Teen And Up Audiences",
            "warnings": ["Graphic Depictions Of Violence"],
            "language": "en",
            "status": "complete",
            "series": "Series A",
            "series_index": 2,
            "published_at": "2026-03-23",
            "fandoms": ["Fandom A"],
            "relationships": ["A/B"],
            "characters": ["Alice"],
            "freeform_tags": ["Adventure"],
        },
        editor_username="alice",
        edited_by_admin=True,
    )

    repository.add_work_comment("work-1", "alice", "Great work", chapter_number=1)
    assert repository.add_work_kudo("work-1", "alice") is True
    assert repository.add_work_kudo("work-1", "alice") is False

    work = repository.get_work("work-1")
    assert work is not None
    assert str(work["title"]) == "Updated Title"
    assert repository.has_user_kudoed_work("work-1", "alice") is True
    assert repository.work_kudos_count("work-1") == 1

    comments = repository.list_work_comments("work-1")
    assert len(comments) == 1
    assert comments[0]["chapter_number"] == 1
    assert comments[0]["commenter_display_name"] == "alice"

    notification_id = repository.create_notification(
        "alice",
        actor_username="bob",
        work_id="work-1",
        kind="comment",
        message="bob commented on your work.",
        href="/comic/work-1",
    )
    assert notification_id > 0
    assert repository.count_unread_notifications("alice") == 1
    notification_rows = repository.list_user_notifications("alice", limit=10)
    assert len(notification_rows) == 1
    assert notification_rows[0]["kind"] == "comment"
    assert notification_rows[0]["actor_display_name"] == "bob"
    assert notification_rows[0]["is_read"] is False
    assert repository.mark_notification_read("alice", notification_id) is True
    assert repository.count_unread_notifications("alice") == 0
    assert repository.mark_all_notifications_read("alice") == 0
    assert repository.delete_notification("alice", notification_id) is True
    assert repository.list_user_notifications("alice", limit=10) == []

    tags = work.get("tags", [])
    assert isinstance(tags, list)
    tag_items = cast(list[object], tags)
    assert any(_is_fandom_tag(tag) for tag in tag_items)
    assert "Fandom A" in repository.list_tag_names("fandom")

    page_files = repository.get_page_files("work-1", 1)
    assert page_files is not None
    assert str(page_files["image"]) == "p1.jpg"
    assert repository.list_work_page_image_names("work-1") == ["p1.jpg", "p2.jpg"]

    works = repository.list_works({"q": "Updated", "status": "complete", "sort": "title_asc"})
    assert len(works) == 1
    assert works[0]["id"] == "work-1"

    partial_fandom_matches = repository.list_works({"fandom": "fandom", "include_mature": "1", "include_explicit": "1"})
    assert any(work["id"] == "work-1" for work in partial_fandom_matches)

    partial_tag_matches = repository.list_works({"tag": "adven", "include_mature": "1", "include_explicit": "1"})
    assert any(work["id"] == "work-1" for work in partial_tag_matches)

    user_matches = repository.list_works({"user": "ALI", "include_mature": "1", "include_explicit": "1"})
    assert any(work["id"] == "work-1" for work in user_matches)

    works_by_uploader = repository.list_works_by_uploader("alice")
    assert len(works_by_uploader) == 1

    version_manifest = repository.create_work_version_snapshot(
        "work-1",
        action="metadata-update",
        actor="alice",
        details={"reason": "test"},
    )
    assert version_manifest is not None
    version_id = str(version_manifest["version_id"])

    versions = repository.list_work_versions("work-1", limit=10)
    assert len(versions) == 1
    assert versions[0]["version_id"] == version_id

    loaded_manifest = repository.get_work_version_manifest("work-1", version_id)
    assert loaded_manifest is not None
    assert loaded_manifest["version_id"] == version_id
    assert repository.get_work_version_manifest("work-1", "../bad") is None

    manifest = repository.get_manifest("work-1")
    assert manifest is not None
    assert manifest["current_version_id"] == version_id
    assert isinstance(manifest["pages"], list)

    metadata_toml = repository.WORKS_DIR / "work-1" / "metadata.toml"
    assert metadata_toml.exists()


def test_tag_suggestions_use_usage_then_seed_popularity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)
    _seed_work(repository)

    repository.update_work_metadata(
        "work-1",
        {
            "title": "Updated Title",
            "summary": "Updated Summary",
            "rating": "Teen And Up Audiences",
            "warnings": ["No Archive Warnings Apply"],
            "language": "en",
            "status": "in_progress",
            "series": "Series A",
            "series_index": 1,
            "published_at": "2026-03-23",
            "fandoms": ["Fandom A"],
            "relationships": [],
            "characters": [],
            "freeform_tags": ["Adventure"],
        },
        editor_username="alice",
        edited_by_admin=False,
    )

    with repository.get_connection() as connection:
        adventurous_id = repository._ensure_tag("Adventurous", "freeform", connection=connection)
        adverb_id = repository._ensure_tag("Adverb", "freeform", connection=connection)
        connection.execute(
            "INSERT INTO tag_popularity (tag_id, seed_count, usage_count) VALUES (?, ?, ?)"
            " ON CONFLICT(tag_id) DO UPDATE SET seed_count = excluded.seed_count, usage_count = excluded.usage_count",
            (adventurous_id, 100, 0),
        )
        connection.execute(
            "INSERT INTO tag_popularity (tag_id, seed_count, usage_count) VALUES (?, ?, ?)"
            " ON CONFLICT(tag_id) DO UPDATE SET seed_count = excluded.seed_count, usage_count = excluded.usage_count",
            (adverb_id, 50, 0),
        )

    initial_suggestions = repository.list_tag_name_suggestions("freeform", "adv", limit=3)
    assert initial_suggestions == ["Adventure", "Adventurous", "Adverb"]

    with repository.get_connection() as connection:
        adventure_row = connection.execute(
            """
            SELECT tp.usage_count
            FROM tag_popularity AS tp
            JOIN tags AS t ON t.id = tp.tag_id
            WHERE t.slug = 'adventure'
            """
        ).fetchone()
    assert adventure_row is not None
    assert int(adventure_row["usage_count"]) == 1

    repository.update_work_metadata(
        "work-1",
        {
            "title": "Updated Title",
            "summary": "Updated Summary",
            "rating": "Teen And Up Audiences",
            "warnings": ["No Archive Warnings Apply"],
            "language": "en",
            "status": "in_progress",
            "series": "Series A",
            "series_index": 1,
            "published_at": "2026-03-23",
            "fandoms": ["Fandom A"],
            "relationships": [],
            "characters": [],
            "freeform_tags": ["Adventure", "Adventurous"],
        },
        editor_username="alice",
        edited_by_admin=False,
    )

    with repository.get_connection() as connection:
        rows = connection.execute(
            """
            SELECT t.slug, tp.usage_count
            FROM tag_popularity AS tp
            JOIN tags AS t ON t.id = tp.tag_id
            WHERE t.slug IN ('adventure', 'adventurous')
            ORDER BY t.slug ASC
            """
        ).fetchall()
    assert len(rows) == 2
    assert int(rows[0]["usage_count"]) == 1
    assert int(rows[1]["usage_count"]) == 1


def test_backfill_tag_usage_counts_and_popularity_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)
    _seed_work(repository, work_id="work-1")
    _seed_work(repository, work_id="work-2")

    repository.update_work_metadata(
        "work-1",
        {
            "title": "Updated Title",
            "summary": "Updated Summary",
            "rating": "Teen And Up Audiences",
            "warnings": ["No Archive Warnings Apply"],
            "language": "en",
            "status": "in_progress",
            "series": "Series A",
            "series_index": 1,
            "published_at": "2026-03-23",
            "fandoms": ["Fandom A"],
            "relationships": [],
            "characters": [],
            "freeform_tags": ["Adventure"],
        },
        editor_username="alice",
        edited_by_admin=False,
    )
    repository.update_work_metadata(
        "work-2",
        {
            "title": "Updated Title 2",
            "summary": "Updated Summary 2",
            "rating": "Teen And Up Audiences",
            "warnings": ["No Archive Warnings Apply"],
            "language": "en",
            "status": "in_progress",
            "series": "Series A",
            "series_index": 1,
            "published_at": "2026-03-23",
            "fandoms": ["Fandom A"],
            "relationships": [],
            "characters": [],
            "freeform_tags": ["Adventure", "Adventurous"],
        },
        editor_username="alice",
        edited_by_admin=False,
    )

    with repository.get_connection() as connection:
        adventurous_id = repository._ensure_tag("Adventurous", "freeform", connection=connection)
        connection.execute(
            "INSERT INTO tag_popularity (tag_id, seed_count, usage_count) VALUES (?, ?, ?)"
            " ON CONFLICT(tag_id) DO UPDATE SET seed_count = excluded.seed_count, usage_count = excluded.usage_count",
            (adventurous_id, 999, 0),
        )

    updated_total = repository.backfill_tag_usage_counts_from_work_tags()
    assert updated_total >= 2

    rows = repository.list_top_tag_popularity(limit=5, tag_type="freeform", query="adv")
    assert len(rows) >= 2
    assert rows[0]["name"] == "Adventurous"
    assert rows[0]["seed_count"] == 999
    assert rows[0]["usage_count"] == 1
    assert rows[0]["effective_popularity"] == 1000


def test_chapters_progress_and_delete_work_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)
    seeded = _seed_work(repository)

    cbz_path = Path(str(seeded["cbz_path"]))
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    cbz_path.write_bytes(b"cbz")

    repository.replace_work_pages(
        "work-1",
        [
            {
                "page_index": 1,
                "image_filename": "p1.jpg",
                "thumb_filename": None,
                "width": 1000,
                "height": 1500,
            },
            {
                "page_index": 2,
                "image_filename": "p2.jpg",
                "thumb_filename": None,
                "width": 1000,
                "height": 1500,
            },
        ],
    )

    chapter = repository.add_work_chapter("work-1", "Chapter 1", 1, 2)
    chapter_id = int(chapter["id"])
    members = repository.list_work_chapter_members(chapter_id)
    assert members == ["p1.jpg", "p2.jpg"]

    repository.replace_work_chapter_members(chapter_id, ["p2.jpg"])
    assert repository.list_work_chapter_members(chapter_id) == ["p2.jpg"]

    updated = repository.update_work_chapter("work-1", chapter_id, "Renamed", 1, 1)
    assert updated is True
    assert repository.update_work_chapter("work-1", 999_999, "Missing", 1, 1) is False

    assert repository.delete_work_chapter("work-1", chapter_id) is True
    assert repository.delete_work_chapter("work-1", chapter_id) is False

    repository.save_progress("work-1", "alice", 2)
    assert repository.load_progress("work-1", "alice") == 2
    assert repository.load_progress("work-1", "bob") == 1

    work_dir = repository.WORKS_DIR / "work-1"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "placeholder.txt").write_text("x", encoding="utf-8")

    assert repository.delete_work("work-1") is True
    assert repository.delete_work("work-1") is False
    assert cbz_path.exists() is False
    assert work_dir.exists() is False


def test_fanart_crud_and_lookup_helpers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    item_id = repository.create_fanart_item(
        item_id="fanart-1",
        uploader_username="alice",
        title="Clouds",
        summary="Paint study",
        fandom="Skyverse",
        rating="Mature",
        image_filename="_objects/ab/image.avif",
        thumb_filename="_objects/ab/thumb.avif",
        width=1280,
        height=720,
    )
    assert item_id == "fanart-1"

    repository.create_fanart_item(
        item_id="fanart-2",
        uploader_username="bob",
        title="Robots",
        summary="",
        fandom="MechaVerse",
        image_filename="_objects/cd/image.avif",
        thumb_filename="_objects/cd/thumb.avif",
        width=640,
        height=480,
    )

    users = repository.list_fanart_users(limit=20)
    assert len(users) == 2
    assert users[0]["uploader_username"] == "alice"
    assert users[0]["latest_item_id"] == "fanart-1"
    assert users[0]["latest_thumb_filename"] == "_objects/ab/thumb.avif"

    filtered_users = repository.list_fanart_users({"q": "robot"}, limit=20)
    assert len(filtered_users) == 1
    assert filtered_users[0]["uploader_username"] == "bob"

    user_filtered_users = repository.list_fanart_users({"user": "ALI"}, limit=20)
    assert len(user_filtered_users) == 1
    assert user_filtered_users[0]["uploader_username"] == "alice"

    user_filtered_users_csv = repository.list_fanart_users({"user": "ALI, bo"}, limit=20)
    assert len(user_filtered_users_csv) == 2
    assert {row["uploader_username"] for row in user_filtered_users_csv} == {
        "alice",
        "bob",
    }

    fandom_users = repository.list_fanart_users({"fandom": "skyverse"}, limit=20)
    assert len(fandom_users) == 1
    assert fandom_users[0]["uploader_username"] == "alice"

    fandom_users_csv = repository.list_fanart_users({"fandom": "skyverse, mech"}, limit=20)
    assert len(fandom_users_csv) == 2
    assert {row["uploader_username"] for row in fandom_users_csv} == {"alice", "bob"}

    complete_users = repository.list_fanart_users({"status": "complete"}, limit=20)
    assert len(complete_users) == 1
    assert complete_users[0]["uploader_username"] == "alice"

    in_progress_users = repository.list_fanart_users(
        {"status": "in_progress"},
        limit=20,
    )
    assert len(in_progress_users) == 1
    assert in_progress_users[0]["uploader_username"] == "bob"

    sorted_users = repository.list_fanart_users({"sort": "title_asc"}, limit=20)
    assert [row["uploader_username"] for row in sorted_users] == ["alice", "bob"]

    filtered_items = repository.list_fanart_items({"q": "robot"}, limit=20)
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == "fanart-2"
    assert filtered_items[0]["uploader_display_name"] == "bob"

    user_items = repository.list_fanart_items({"user": "ali"}, limit=20)
    assert len(user_items) == 1
    assert user_items[0]["id"] == "fanart-1"

    user_items_case = repository.list_fanart_items({"user": "ALI"}, limit=20)
    assert len(user_items_case) == 1
    assert user_items_case[0]["id"] == "fanart-1"

    user_items_csv = repository.list_fanart_items({"user": "ALI, bo"}, limit=20)
    assert len(user_items_csv) == 2
    assert {row["id"] for row in user_items_csv} == {"fanart-1", "fanart-2"}

    fandom_items = repository.list_fanart_items({"fandom": "skyverse"}, limit=20)
    assert len(fandom_items) == 1
    assert fandom_items[0]["id"] == "fanart-1"

    fandom_items_csv = repository.list_fanart_items({"fandom": "skyverse, mech"}, limit=20)
    assert len(fandom_items_csv) == 2
    assert {row["id"] for row in fandom_items_csv} == {"fanart-1", "fanart-2"}

    partial_tag_items = repository.list_fanart_items({"tag": "sky"}, limit=20)
    assert len(partial_tag_items) == 1
    assert partial_tag_items[0]["id"] == "fanart-1"

    partial_tag_items_csv = repository.list_fanart_items({"tag": "sky, robot"}, limit=20)
    assert len(partial_tag_items_csv) == 2
    assert {row["id"] for row in partial_tag_items_csv} == {"fanart-1", "fanart-2"}

    complete_items = repository.list_fanart_items({"status": "complete"}, limit=20)
    assert len(complete_items) == 1
    assert complete_items[0]["id"] == "fanart-1"

    in_progress_items = repository.list_fanart_items(
        {"status": "in_progress"},
        limit=20,
    )
    assert len(in_progress_items) == 1
    assert in_progress_items[0]["id"] == "fanart-2"

    items = repository.list_fanart_items_by_uploader("alice", limit=20)
    assert len(items) == 1
    assert items[0]["id"] == "fanart-1"
    assert items[0]["uploader_display_name"] == "alice"

    item_by_id = repository.get_fanart_item("fanart-1")
    assert item_by_id is not None
    assert item_by_id["image_filename"] == "_objects/ab/image.avif"
    assert item_by_id["fandom"] == "Skyverse"
    assert item_by_id["rating"] == "Mature"

    item_by_image = repository.get_fanart_item_by_image("alice", "_objects/ab/image.avif")
    assert item_by_image is not None
    assert item_by_image["id"] == "fanart-1"

    item_by_image_filename = repository.get_fanart_item_by_image_filename("_objects/ab/image.avif")
    assert item_by_image_filename is not None
    assert item_by_image_filename["uploader_display_name"] == "alice"

    item_by_image_legacy = repository.get_fanart_item_by_image("alice", "/_objects/ab/image.avif")
    assert item_by_image_legacy is not None
    assert item_by_image_legacy["id"] == "fanart-1"

    item_by_thumb = repository.get_fanart_item_by_thumb("alice", "_objects/ab/thumb.avif")
    assert item_by_thumb is not None
    assert item_by_thumb["id"] == "fanart-1"
    item_by_thumb_legacy = repository.get_fanart_item_by_thumb("alice", "/_objects/ab/thumb.avif")
    assert item_by_thumb_legacy is not None
    assert item_by_thumb_legacy["id"] == "fanart-1"

    assert repository.delete_fanart_item("fanart-1") is True
    assert repository.get_fanart_item("fanart-1") is None
    assert repository.delete_fanart_item("fanart-1") is False

    assert repository.fanart_file_for("_objects/ab/image.avif") == (
        repository.FANART_DIR / "images" / "_objects/ab/image.avif"
    )
    assert repository.fanart_file_for("/_objects/ab/image.avif") == (
        repository.FANART_DIR / "images" / "_objects/ab/image.avif"
    )
    assert repository.fanart_thumb_for("_objects/ab/thumb.avif") == (
        repository.FANART_DIR / "thumbs" / "_objects/ab/thumb.avif"
    )
    assert repository.fanart_thumb_for("/_objects/ab/thumb.avif") == (
        repository.FANART_DIR / "thumbs" / "_objects/ab/thumb.avif"
    )


def test_user_role_management_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    assert repository.get_user_role("alice") == "guest"

    repository.create_user(
        "alice",
        display_name="Alice",
        email="alice@example.com",
        role="user",
        active=True,
    )
    assert repository.get_user_role("alice") == "user"

    assert repository.set_user_role("alice", "admin") is True
    assert repository.get_user_role("alice") == "admin"

    assert repository.set_user_active("alice", False) is True
    assert repository.get_user_role("alice") == "guest"

    assert repository.set_user_active("alice", True) is True
    assert repository.get_user_role("alice") == "admin"

    with pytest.raises(ValueError):
        repository.set_user_role("alice", "guest")

    with pytest.raises(ValueError):
        repository.create_user(
            "",
            display_name="",
            email=None,
            role="user",
            active=True,
        )


def test_create_user_rejects_duplicate_email_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    repository.create_user(
        "alice",
        display_name="Alice",
        email="Alice@Example.com",
        role="user",
        active=True,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.create_user(
            "bob",
            display_name="Bob",
            email="alice@example.com",
            role="user",
            active=True,
        )


def test_create_user_rejects_non_alphanumeric_display_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        repository.create_user(
            "alice",
            display_name="Alice Smith",
            email="alice@example.com",
            role="user",
            active=True,
        )


def test_create_user_rejects_duplicate_display_name_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _init_repository_module(monkeypatch, tmp_path)

    repository.create_user(
        "alice",
        display_name="Alice",
        email="alice@example.com",
        role="user",
        active=True,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.create_user(
            "bob",
            display_name="alice",
            email="bob@example.com",
            role="user",
            active=True,
        )
