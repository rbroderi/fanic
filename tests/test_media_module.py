from pathlib import Path

import niquests as requests
import pytest

from fanic.media import BunnyStorageMediaBackend
from fanic.media import LocalMediaBackend
from fanic.media import MediaService
from fanic.media import media_public_path_from_key
from fanic.media import normalize_media_key
from fanic.settings import FANART_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import get_settings


class _DummySettings:
    media_base_url: str = "https://fanic.media"
    media_cdn_base_url: str = "https://media.fanic.media"
    media_backend: str = "local"
    media_bunny_storage_zone: str = ""
    media_bunny_pull_zone: str = ""
    media_bunny_api_key_ro: str = ""
    media_bunny_api_key_rw: str = ""
    media_bunny_timeout_seconds: float = 30.0


def test_normalize_media_key_accepts_static_and_relative_forms() -> None:
    assert normalize_media_key("/static/work-1/pages/001.avif") == "work-1/pages/001.avif"
    assert normalize_media_key("static/fanart/images/a.avif") == "fanart/images/a.avif"
    assert normalize_media_key("fanart/thumbs/t.avif") == "fanart/thumbs/t.avif"


def test_local_media_backend_crud_and_url_mapping(tmp_path: Path) -> None:
    backend = LocalMediaBackend(
        works_root=tmp_path / "works",
        fanart_root=tmp_path / "fanart",
    )
    service = MediaService(settings=_DummySettings(), backend=backend)

    key = service.comic_page_key("work-1", "001.avif")
    service.put_bytes(key, b"hello", "image/avif")
    assert service.exists(key) is True
    assert service.get_bytes(key) == b"hello"

    local_path = service.local_path_for_key(key)
    assert local_path is not None
    assert local_path == (tmp_path / "works" / "work-1" / "pages" / "001.avif").resolve()

    assert service.public_path_for_key(key) == "/static/work-1/pages/001.avif"
    assert service.media_url(key) == "https://media.fanic.media/static/work-1/pages/001.avif"

    assert service.media_url("/static/logo.png") == "https://fanic.media/static/logo.png"

    service.delete(key)
    assert service.exists(key) is False


def test_local_media_backend_maps_fanart_into_fanart_root(tmp_path: Path) -> None:
    backend = LocalMediaBackend(
        works_root=tmp_path / "works",
        fanart_root=tmp_path / "fanart",
    )
    service = MediaService(settings=_DummySettings(), backend=backend)

    key = service.fanart_thumb_key("_objects/aa/thumb.avif")
    service.put_bytes(key, b"thumb")

    local_path = service.local_path_for_key(key)
    assert local_path is not None
    assert local_path == (tmp_path / "fanart" / "thumbs" / "_objects" / "aa" / "thumb.avif").resolve()


def test_media_url_uses_media_base_when_cdn_is_disabled(tmp_path: Path) -> None:
    class _NoCdnSettings(_DummySettings):
        media_cdn_base_url: str = ""

    backend = LocalMediaBackend(
        works_root=tmp_path / "works",
        fanart_root=tmp_path / "fanart",
    )
    service = MediaService(settings=_NoCdnSettings(), backend=backend)

    assert service.media_url("/static/fanart/images/demo.avif") == "https://fanic.media/static/fanart/images/demo.avif"


def test_bunny_backend_object_url_places_media_under_static_prefix() -> None:
    backend = BunnyStorageMediaBackend(
        read_api_key="test-ro",  # pragma: allowlist secret
        write_api_key="test-rw",  # pragma: allowlist secret
        storage_zone="zone-a",
        storage_base_url="https://storage.bunnycdn.com",
        timeout_seconds=5.0,
    )

    assert (
        backend.object_url_for_key("fanart/images/test.avif")
        == "https://storage.bunnycdn.com/zone-a/static/fanart/images/test.avif"
    )


def test_media_public_path_from_key() -> None:
    assert media_public_path_from_key("fanart/images/demo.avif") == "/static/fanart/images/demo.avif"


def test_normalize_media_key_rejects_empty_and_absolute_urls() -> None:
    with pytest.raises(ValueError):
        _ = normalize_media_key("")
    with pytest.raises(ValueError):
        _ = normalize_media_key("https://example.com/x.avif")


def test_local_media_backend_skips_managed_runtime_mutation_under_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_VERSION", "1")
    monkeypatch.delenv("FANIC_ALLOW_PYTEST_MEDIA_MUTATIONS", raising=False)

    backend = LocalMediaBackend(
        works_root=WORKS_DIR,
        fanart_root=FANART_DIR,
    )

    key = "test-work/pages/test.avif"
    backend.put_bytes(key, b"should-not-write")
    assert backend.exists(key) is False


def test_bunny_media_backend_skips_remote_mutation_under_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_VERSION", "1")
    monkeypatch.delenv("FANIC_ALLOW_PYTEST_MEDIA_MUTATIONS", raising=False)

    backend = BunnyStorageMediaBackend(
        read_api_key="test-ro",  # pragma: allowlist secret
        write_api_key="test-rw",  # pragma: allowlist secret
        storage_zone="zone-a",
        timeout_seconds=1.0,
    )

    def _session_put_fail(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("session.put should not be called when pytest mutation guard is active")

    monkeypatch.setattr(backend.session, "put", _session_put_fail)

    backend.put_bytes("fanart/images/test.avif", b"data", "image/avif")


def test_bunny_storage_api_auth_get_root_live() -> None:
    """Mandatory Bunny auth check using configured storage endpoint and credential files."""

    settings = get_settings()
    storage_zone = settings.media_bunny_storage_zone.strip()
    storage_api_base_url = settings.media_bunny_storage_api_base_url.strip()

    assert storage_zone, "media_bunny_storage_zone must be configured"
    assert storage_api_base_url, "media_bunny_storage_api_base_url must be configured"

    credential_paths = [
        Path("/etc/fanic/credentials/bunnystorage_ro"),  # pragma: allowlist secret
        Path("/etc/fanic/credentials/bunnystorage_rw"),  # pragma: allowlist secret
    ]

    for credential_path in credential_paths:
        assert credential_path.exists(), f"Missing Bunny credential file: {credential_path}"
        access_key = credential_path.read_text(encoding="utf-8").strip()
        assert access_key, f"Bunny credential file is empty: {credential_path}"

        endpoint = f"{storage_api_base_url.rstrip('/')}/{storage_zone}/"
        response = requests.get(
            endpoint,
            headers={
                "AccessKey": access_key,
                "Accept": "application/json",
            },
            timeout=10,
        )
        response_text = response.text if response.text is not None else ""

        assert response.status_code == 200, (
            f"Bunny auth failed for {credential_path} at {endpoint} "
            f"status={response.status_code} body={response_text[:200]}"
        )
