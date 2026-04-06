"""Media storage abstraction for comic and fanart objects.

This module provides a unified interface for CRUD operations on media objects
and consistent public URL generation. It supports the current local filesystem
layout and an opt-in Bunny Storage backend for migration.
"""

import os
import shutil
from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from typing import runtime_checkable
from urllib.parse import quote

import niquests as requests
from niquests.adapters import HTTPAdapter

from fanic.settings import FANART_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import FanicSettings
from fanic.settings import get_settings

_SETTINGS = get_settings()
_MANAGED_RUNTIME_ROOT = _SETTINGS.data_root.resolve()
_MANAGED_LOCAL_MUTATION_ROOTS = (WORKS_DIR.resolve(), FANART_DIR.resolve())


def _running_under_pytest() -> bool:
    return True if os.environ.get("PYTEST_VERSION") else False


def _allow_pytest_media_mutations() -> bool:
    return (
        True
        if (
            os.environ.get("FANIC_ALLOW_PYTEST_MEDIA_MUTATIONS")
            or os.environ.get("FANIC_ALLOW_PYTEST_FILESYSTEM_MUTATIONS")
        )
        else False
    )


def _is_managed_runtime_path(path: Path) -> bool:
    try:
        _ = path.resolve().relative_to(_MANAGED_RUNTIME_ROOT)
    except ValueError:
        return False
    return True


def _is_managed_runtime_local_path(path: Path) -> bool:
    resolved = path.resolve()
    for root in _MANAGED_LOCAL_MUTATION_ROOTS:
        try:
            _ = resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _should_skip_local_mutation_for_tests(path: Path) -> bool:
    if not _running_under_pytest():
        return False
    if _allow_pytest_media_mutations():
        return False
    return True if _is_managed_runtime_local_path(path) else False


def _should_skip_filesystem_mutation_for_tests(path: Path) -> bool:
    if not _running_under_pytest():
        return False
    if _allow_pytest_media_mutations():
        return False
    return True if _is_managed_runtime_path(path) else False


def delete_file(path: Path, *, missing_ok: bool = False) -> None:
    if _should_skip_filesystem_mutation_for_tests(path):
        return
    path.unlink(missing_ok=missing_ok)


def delete_tree(path: Path, *, ignore_errors: bool = False) -> None:
    if _should_skip_filesystem_mutation_for_tests(path):
        return
    shutil.rmtree(path, ignore_errors=ignore_errors)


def copy_file(src: Path, dst: Path) -> Path:
    if _should_skip_filesystem_mutation_for_tests(dst):
        return dst
    return Path(shutil.copy2(src, dst))


def copy_tree(src: Path, dst: Path) -> Path:
    if _should_skip_filesystem_mutation_for_tests(dst):
        return dst
    return Path(shutil.copytree(src, dst))


def _should_skip_remote_mutation_for_tests() -> bool:
    if not _running_under_pytest():
        return False
    return False if _allow_pytest_media_mutations() else True


def normalize_media_key(key: str) -> str:
    trimmed = key.strip()
    if not trimmed:
        raise ValueError("Media key cannot be empty")
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        raise ValueError("Media key cannot be an absolute URL")
    trimmed = trimmed.removeprefix("/")
    trimmed = trimmed.removeprefix("static/")
    normalized = trimmed.strip("/")
    if not normalized:
        raise ValueError("Media key cannot be empty")
    return normalized


def media_public_path_from_key(key: str) -> str:
    normalized = normalize_media_key(key)
    return f"/static/{normalized}"


@runtime_checkable
class MediaBackend(Protocol):
    def get_bytes(self, key: str) -> bytes: ...

    def put_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...

    def local_path_for_key(self, key: str) -> Path | None: ...


@runtime_checkable
class MediaSettingsLike(Protocol):
    media_base_url: str
    media_cdn_base_url: str


@dataclass(slots=True)
class LocalMediaBackend:
    works_root: Path
    fanart_root: Path

    def _resolve_local_path(self, key: str) -> Path:
        normalized = normalize_media_key(key)
        works_root = self.works_root.resolve()
        fanart_root = self.fanart_root.resolve()

        if normalized.startswith("fanart/"):
            rel_path = normalized[len("fanart/") :]
            candidate = (fanart_root / rel_path).resolve()
            base = fanart_root
        else:
            candidate = (works_root / normalized).resolve()
            base = works_root

        try:
            _ = candidate.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Media key escapes storage root: {key}") from exc

        return candidate

    def get_bytes(self, key: str) -> bytes:
        path = self._resolve_local_path(key)
        return path.read_bytes()

    def put_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        _ = content_type
        path = self._resolve_local_path(key)
        if _should_skip_local_mutation_for_tests(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(self, key: str) -> None:
        path = self._resolve_local_path(key)
        if _should_skip_local_mutation_for_tests(path):
            return
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        path = self._resolve_local_path(key)
        return path.exists()

    def local_path_for_key(self, key: str) -> Path | None:
        return self._resolve_local_path(key)


@dataclass(slots=True)
class BunnyStorageMediaBackend:
    read_api_key: str
    storage_zone: str
    write_api_key: str = ""
    storage_base_url: str = "https://storage.bunnycdn.com"
    timeout_seconds: float = 30.0
    session: requests.Session = field(default_factory=requests.Session, repr=False)

    def __post_init__(self) -> None:
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _object_path(self, key: str) -> str:
        normalized = normalize_media_key(key)
        return f"static/{normalized}"

    def _object_url(self, key: str) -> str:
        object_path = quote(self._object_path(key), safe="/")
        return f"{self.storage_base_url.rstrip('/')}/{self.storage_zone}/{object_path}"

    def object_url_for_key(self, key: str) -> str:
        return self._object_url(key)

    @property
    def _read_headers(self) -> dict[str, str]:
        return {
            "AccessKey": self.read_api_key,
            "Accept": "application/json",
        }

    @property
    def _write_headers(self) -> dict[str, str]:
        write_key = self.write_api_key.strip()
        if not write_key:
            raise RuntimeError("Bunny write operation requested but media_bunny_api_key_rw is empty")
        return {
            "AccessKey": write_key,
            "Accept": "application/json",
        }

    def get_bytes(self, key: str) -> bytes:
        response = self.session.get(
            self._object_url(key),
            headers=self._read_headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.content if response.content is not None else b""

    def put_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        if _should_skip_remote_mutation_for_tests():
            return
        headers = dict(self._write_headers)
        headers["Content-Type"] = content_type
        response = self.session.put(
            self._object_url(key),
            headers=headers,
            data=content,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def delete(self, key: str) -> None:
        if _should_skip_remote_mutation_for_tests():
            return
        response = self.session.delete(
            self._object_url(key),
            headers=self._write_headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

    def exists(self, key: str) -> bool:
        response = self.session.head(
            self._object_url(key),
            headers=self._read_headers,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False

        # Some object stores do not support HEAD consistently.
        fallback = self.session.get(
            self._object_url(key),
            headers=self._read_headers,
            timeout=self.timeout_seconds,
            stream=True,
        )
        if fallback.status_code == 200:
            return True
        if fallback.status_code == 404:
            return False
        fallback.raise_for_status()
        return True

    def local_path_for_key(self, key: str) -> Path | None:
        _ = key
        return None


@dataclass(slots=True)
class MediaService:
    settings: MediaSettingsLike
    backend: MediaBackend

    @staticmethod
    def _is_image_public_path(public_path: str) -> bool:
        normalized = public_path.strip()
        if not normalized.startswith("/static/"):
            return False

        if normalized.startswith("/static/fanart/images/"):
            return True
        if normalized.startswith("/static/fanart/thumbs/"):
            return True

        static_tail = normalized[len("/static/") :]
        work_id, sep, remainder = static_tail.partition("/")
        if not sep or not work_id:
            return False
        return True if remainder.startswith("pages/") or remainder.startswith("thumbs/") else False

    def comic_page_key(self, work_id: str, image_name: str) -> str:
        safe_work_id = quote(str(work_id).strip(), safe="")
        safe_image_name = quote(str(image_name).strip(), safe="/")
        return f"{safe_work_id}/pages/{safe_image_name}"

    def comic_thumb_key(self, work_id: str, thumb_name: str) -> str:
        safe_work_id = quote(str(work_id).strip(), safe="")
        safe_thumb_name = quote(str(thumb_name).strip(), safe="/")
        return f"{safe_work_id}/thumbs/{safe_thumb_name}"

    def fanart_image_key(self, image_name: str) -> str:
        safe_image_name = quote(str(image_name).strip(), safe="/")
        return f"fanart/images/{safe_image_name}"

    def fanart_thumb_key(self, thumb_name: str) -> str:
        safe_thumb_name = quote(str(thumb_name).strip(), safe="/")
        return f"fanart/thumbs/{safe_thumb_name}"

    def public_path_for_key(self, key: str) -> str:
        return media_public_path_from_key(key)

    def media_url(self, path_or_key: str) -> str:
        trimmed = path_or_key.strip()
        if not trimmed:
            return ""
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            return trimmed

        if trimmed.startswith("/"):
            public_path = trimmed
        elif trimmed.startswith("static/"):
            public_path = f"/{trimmed}"
        else:
            public_path = self.public_path_for_key(trimmed)

        media_cdn_base = self.settings.media_cdn_base_url.strip()
        if media_cdn_base and self._is_image_public_path(public_path):
            return f"{media_cdn_base.rstrip('/')}{public_path}"

        media_base = self.settings.media_base_url.strip()
        if not media_base:
            return public_path
        return f"{media_base.rstrip('/')}{public_path}"

    def get_bytes(self, key: str) -> bytes:
        return self.backend.get_bytes(key)

    def put_bytes(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        self.backend.put_bytes(key, content, content_type)

    def delete(self, key: str) -> None:
        self.backend.delete(key)

    def exists(self, key: str) -> bool:
        return self.backend.exists(key)

    def local_path_for_key(self, key: str) -> Path | None:
        return self.backend.local_path_for_key(key)


def build_media_service(settings: FanicSettings) -> MediaService:
    backend_name = settings.media_backend.strip().lower()
    if backend_name == "bunny":
        read_api_key = settings.media_bunny_api_key_ro.strip()
        write_api_key = settings.media_bunny_api_key_rw.strip()
        storage_zone = settings.media_bunny_storage_zone.strip()

        if not read_api_key:
            raise RuntimeError("media_backend is bunny but media_bunny_api_key_ro is empty")
        if not write_api_key:
            raise RuntimeError("media_backend is bunny but media_bunny_api_key_rw is empty")
        if not storage_zone:
            raise RuntimeError("media_backend is bunny but media_bunny_storage_zone is empty")

        backend: MediaBackend = BunnyStorageMediaBackend(
            read_api_key=read_api_key,
            storage_zone=storage_zone,
            write_api_key=write_api_key,
            storage_base_url=settings.media_bunny_storage_api_base_url,
            timeout_seconds=settings.media_bunny_timeout_seconds,
        )
    else:
        backend = LocalMediaBackend(works_root=WORKS_DIR, fanart_root=FANART_DIR)

    return MediaService(settings=settings, backend=backend)


@lru_cache(maxsize=1)
def get_media_service() -> MediaService:
    return build_media_service(_SETTINGS)
