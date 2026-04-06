#!/opt/fanic/.venv/bin/python
"""One-off migration of local image files to Bunny Storage via REST API.

This script uploads persisted comic/fanart image assets from local runtime
storage to Bunny Storage under the canonical `static/` object prefix.
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path

from fanic.media import BunnyStorageMediaBackend
from fanic.settings import FANART_DIR
from fanic.settings import WORKS_DIR
from fanic.settings import get_settings

_ALLOWED_IMAGE_SUFFIXES = {
    ".avif",
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


@dataclass(slots=True)
class MigrationStats:
    discovered: int = 0
    uploaded: int = 0
    skipped_existing: int = 0
    failed: int = 0


def _is_image_file(path: Path) -> bool:
    return True if path.suffix.lower() in _ALLOWED_IMAGE_SUFFIXES else False


def _content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    return "application/octet-stream"


def _iter_keys_and_paths(
    *, include_comics: bool, include_fanart: bool
) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []

    if include_comics:
        for file_path in WORKS_DIR.rglob("*"):
            if not file_path.is_file() or not _is_image_file(file_path):
                continue
            rel = file_path.relative_to(WORKS_DIR).as_posix()
            # Limit to canonical image folders for works.
            if "/pages/" not in f"/{rel}" and "/thumbs/" not in f"/{rel}":
                continue
            entries.append((rel, file_path))

    if include_fanart:
        images_root = FANART_DIR / "images"
        thumbs_root = FANART_DIR / "thumbs"

        if images_root.exists():
            for file_path in images_root.rglob("*"):
                if not file_path.is_file() or not _is_image_file(file_path):
                    continue
                rel = file_path.relative_to(images_root).as_posix()
                entries.append((f"fanart/images/{rel}", file_path))

        if thumbs_root.exists():
            for file_path in thumbs_root.rglob("*"):
                if not file_path.is_file() or not _is_image_file(file_path):
                    continue
                rel = file_path.relative_to(thumbs_root).as_posix()
                entries.append((f"fanart/thumbs/{rel}", file_path))

    entries.sort(key=lambda item: item[0])
    return entries


def _build_backend(*, storage_api_base_url: str) -> BunnyStorageMediaBackend:
    settings = get_settings()
    read_key = settings.media_bunny_api_key_ro.strip()
    write_key = settings.media_bunny_api_key_rw.strip()
    zone = settings.media_bunny_storage_zone.strip()

    if not read_key:
        raise RuntimeError(
            "media_bunny_api_key_ro is empty; cannot verify remote objects"
        )
    if not write_key:
        raise RuntimeError("media_bunny_api_key_rw is empty; cannot upload objects")
    if not zone:
        raise RuntimeError("media_bunny_storage_zone is empty; cannot upload objects")

    return BunnyStorageMediaBackend(
        read_api_key=read_key,
        write_api_key=write_key,
        storage_zone=zone,
        storage_base_url=storage_api_base_url,
        timeout_seconds=settings.media_bunny_timeout_seconds,
    )


def migrate(
    *,
    dry_run: bool,
    skip_existing: bool,
    limit: int,
    include_comics: bool,
    include_fanart: bool,
    storage_api_base_url: str,
) -> int:
    backend = _build_backend(storage_api_base_url=storage_api_base_url)
    entries = _iter_keys_and_paths(
        include_comics=include_comics,
        include_fanart=include_fanart,
    )

    if limit > 0:
        entries = entries[:limit]

    stats = MigrationStats(discovered=len(entries))
    print(f"Discovered {stats.discovered} image objects for migration")

    for index, (key, file_path) in enumerate(entries, start=1):
        try:
            if dry_run:
                if index <= 20 or index % 500 == 0:
                    print(f"DRY-RUN would upload: {key} <- {file_path}")
                continue

            if skip_existing and backend.exists(key):
                stats.skipped_existing += 1
                if index % 100 == 0:
                    print(
                        f"[{index}/{stats.discovered}] skipped existing={stats.skipped_existing}"
                    )
                continue

            payload = file_path.read_bytes()
            backend.put_bytes(key, payload, content_type=_content_type_for(file_path))
            stats.uploaded += 1

            if index % 100 == 0:
                print(
                    f"[{index}/{stats.discovered}] uploaded={stats.uploaded} "
                    f"skipped={stats.skipped_existing} failed={stats.failed}"
                )
        except Exception as exc:
            stats.failed += 1
            print(f"ERROR key={key} path={file_path} error={exc}", file=sys.stderr)

    print("Migration summary")
    print(f"  discovered: {stats.discovered}")
    print(f"  uploaded: {stats.uploaded}")
    print(f"  skipped_existing: {stats.skipped_existing}")
    print(f"  failed: {stats.failed}")
    if dry_run:
        print("  mode: dry-run")

    return 1 if stats.failed > 0 else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-off migration of local FANIC images to Bunny Storage REST API"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List planned uploads without writing"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Upload even if object already exists remotely",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of files to process (0 means all)",
    )
    parser.add_argument(
        "--only",
        choices=["all", "comics", "fanart"],
        default="all",
        help="Restrict migration scope",
    )
    parser.add_argument(
        "--storage-api-base-url",
        default="https://storage.bunnycdn.com",
        help=(
            "Bunny Storage API base URL. "
            "Use a regional endpoint when needed, for example "
            "https://ny.storage.bunnycdn.com"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    include_comics = args.only in {"all", "comics"}
    include_fanart = args.only in {"all", "fanart"}
    return migrate(
        dry_run=bool(args.dry_run),
        skip_existing=not bool(args.no_skip_existing),
        limit=int(args.limit),
        include_comics=include_comics,
        include_fanart=include_fanart,
        storage_api_base_url=str(args.storage_api_base_url).strip(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
