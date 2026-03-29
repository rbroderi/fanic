#!/usr/bin/env python3
"""Rebuild stored thumbnails for comics and fanart using current settings.

This script uses the configured thumbnail sizing and AVIF quality from settings.toml.
It can run in dry-run mode and can target comics, fanart, or both.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

import pillow_avif  # noqa: F401  # pyright: ignore[reportUnusedImport]  # Register AVIF support with Pillow.
from PIL import Image
from PIL import UnidentifiedImageError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _ensure_src_on_path() -> None:
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))


def _prepare_image_for_avif(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"}:
        return image.convert("RGBA")
    if image.mode == "P":
        return image.convert("RGBA")
    return image.convert("RGB")


def _render_image_bytes(image: Image.Image, *, fmt: str, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, quality=quality)
    return buffer.getvalue()


def _content_addressed_rel_path(data: bytes, extension: str) -> str:
    digest = hashlib.sha256(data).hexdigest()
    normalized_ext = extension.strip().lower().lstrip(".")
    resolved_ext = normalized_ext if normalized_ext else "bin"
    return f"_objects/{digest[:2]}/{digest}.{resolved_ext}"


def _store_content_addressed(base_dir: Path, data: bytes, extension: str) -> str:
    rel_path = _content_addressed_rel_path(data, extension)
    target = (base_dir / rel_path).resolve()
    resolved_base = base_dir.resolve()
    try:
        _ = target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"Upload target escapes fanart storage: {target}") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return rel_path

    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        pass
    return rel_path


def rebuild_fanart_thumbnails(*, dry_run: bool) -> dict[str, object]:
    _ensure_src_on_path()
    from fanic.db import get_connection
    from fanic.settings import FANART_DIR
    from fanic.settings import get_settings

    settings = get_settings()
    thumbnail_max_dimensions = settings.thumbnail_max_dimensions
    thumbnail_quality = int(settings.thumbnail_avif_quality)

    images_dir = FANART_DIR / "images"
    thumbs_dir = FANART_DIR / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, image_filename, thumb_filename
            FROM fanart_items
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()

    scanned = 0
    converted = 0
    unchanged = 0
    missing_source = 0
    failed = 0
    updates: list[tuple[str, str]] = []

    for row in rows:
        scanned += 1
        item_id = str(row["id"])
        image_filename = str(row["image_filename"] if row["image_filename"] else "")
        thumb_filename = str(row["thumb_filename"] if row["thumb_filename"] else "")

        image_path = images_dir / image_filename
        thumb_path = thumbs_dir / thumb_filename if thumb_filename else None
        source_path: Path | None = None
        if image_path.exists():
            source_path = image_path
        elif thumb_path is not None and thumb_path.exists():
            source_path = thumb_path

        if source_path is None:
            missing_source += 1
            continue

        try:
            with Image.open(source_path) as image:
                thumb_image = _prepare_image_for_avif(image)
                thumb_image.thumbnail(thumbnail_max_dimensions)
                thumb_bytes = _render_image_bytes(
                    thumb_image,
                    fmt="AVIF",
                    quality=thumbnail_quality,
                )
        except (UnidentifiedImageError, OSError, ValueError):
            failed += 1
            continue

        new_thumb_name = (
            _content_addressed_rel_path(thumb_bytes, "avif")
            if dry_run
            else _store_content_addressed(thumbs_dir, thumb_bytes, "avif")
        )

        if new_thumb_name == thumb_filename:
            unchanged += 1
            continue

        converted += 1
        updates.append((new_thumb_name, item_id))

    if (not dry_run) and updates:
        with get_connection() as connection:
            connection.executemany(
                """
                UPDATE fanart_items
                SET thumb_filename = ?
                WHERE id = ?
                """,
                updates,
            )

    return {
        "scanned": scanned,
        "converted": converted,
        "unchanged": unchanged,
        "missing_source": missing_source,
        "failed": failed,
        "updated_rows": 0 if dry_run else len(updates),
        "dry_run": dry_run,
        "thumbnail_max_size": f"{thumbnail_max_dimensions[0]}x{thumbnail_max_dimensions[1]}",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild comic and fanart thumbnails using current thumbnail settings."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate changes without writing files or DB updates.",
    )
    parser.add_argument(
        "--scope",
        choices=["all", "comics", "fanart"],
        default="all",
        help="Choose whether to process comics, fanart, or both.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    results: dict[str, Any] = {}
    if args.scope in {"all", "comics"}:
        _ensure_src_on_path()
        from fanic.ingest import convert_existing_thumbs_to_avif

        results["comics"] = convert_existing_thumbs_to_avif(dry_run=bool(args.dry_run))

    if args.scope in {"all", "fanart"}:
        results["fanart"] = rebuild_fanart_thumbnails(dry_run=bool(args.dry_run))

    print(json.dumps(results, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
