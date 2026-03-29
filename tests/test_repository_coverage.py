import sqlite3
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
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
    import fanic.repository as repository

    schema_path = Path(__file__).resolve().parents[1] / "src" / "fanic" / "sql" / "schema.sql"
    db_path = tmp_path / "repo.sqlite3"
    with sqlite3.connect(db_path, factory=_ManagedTestConnection) as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _ensure_test_runtime_schema(connection)

    def get_test_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(db_path, factory=_ManagedTestConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        _ensure_test_runtime_schema(connection)
        return connection

    works_dir = tmp_path / "works"
    cbz_dir = tmp_path / "cbz"
    works_dir.mkdir(parents=True, exist_ok=True)
    cbz_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(repository, "get_connection", get_test_connection)
    monkeypatch.setattr(repository, "WORKS_DIR", works_dir)
    monkeypatch.setattr(repository, "CBZ_DIR", cbz_dir)
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

    monkeypatch.setattr(repository, "get_settings", lambda: _Settings())

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

    monkeypatch.setattr(repository, "get_settings", lambda: _Settings())

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

    notification_id = repository.create_notification(
        "alice",
        actor_username="bob",
        work_id="work-1",
        kind="comment",
        message="bob commented on your work.",
        href="/works/work-1",
    )
    assert notification_id > 0
    assert repository.count_unread_notifications("alice") == 1
    notification_rows = repository.list_user_notifications("alice", limit=10)
    assert len(notification_rows) == 1
    assert notification_rows[0]["kind"] == "comment"
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

    fandom_users = repository.list_fanart_users({"fandom": "skyverse"}, limit=20)
    assert len(fandom_users) == 1
    assert fandom_users[0]["uploader_username"] == "alice"

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

    user_items = repository.list_fanart_items({"user": "ali"}, limit=20)
    assert len(user_items) == 1
    assert user_items[0]["id"] == "fanart-1"

    fandom_items = repository.list_fanart_items({"fandom": "skyverse"}, limit=20)
    assert len(fandom_items) == 1
    assert fandom_items[0]["id"] == "fanart-1"

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

    item_by_id = repository.get_fanart_item("fanart-1")
    assert item_by_id is not None
    assert item_by_id["image_filename"] == "_objects/ab/image.avif"
    assert item_by_id["fandom"] == "Skyverse"
    assert item_by_id["rating"] == "Mature"

    item_by_image = repository.get_fanart_item_by_image("alice", "_objects/ab/image.avif")
    assert item_by_image is not None
    assert item_by_image["id"] == "fanart-1"

    item_by_thumb = repository.get_fanart_item_by_thumb("alice", "_objects/ab/thumb.avif")
    assert item_by_thumb is not None
    assert item_by_thumb["id"] == "fanart-1"

    assert repository.delete_fanart_item("fanart-1") is True
    assert repository.get_fanart_item("fanart-1") is None
    assert repository.delete_fanart_item("fanart-1") is False

    assert repository.fanart_file_for("_objects/ab/image.avif") == (
        repository.FANART_DIR / "images" / "_objects/ab/image.avif"
    )
    assert repository.fanart_thumb_for("_objects/ab/thumb.avif") == (
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
