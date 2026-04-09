#!/opt/fanic/.venv/bin/python
"""One-off cleanup for orphaned Bunny media objects.

This script scans Bunny Storage under the FANIC media zone, computes keys that
should exist from the current database state, and reports/deletes remote keys
that are no longer referenced.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import quote
from urllib.parse import urlsplit

import niquests as requests
from niquests.adapters import HTTPAdapter

from fanic.db import get_connection
from fanic.settings import get_settings


@dataclass(slots=True)
class CleanupStats:
    remote_scanned: int = 0
    expected: int = 0
    orphaned: int = 0
    deleted: int = 0
    failed: int = 0


def _split_path_parts(key: str) -> list[str]:
    normalized = key.strip().strip("/")
    if not normalized:
        return []
    return [part for part in normalized.split("/") if part]


def _is_media_candidate_key(key: str) -> bool:
    parts = _split_path_parts(key)
    if len(parts) < 2:
        return False

    if parts[0] == "fanart":
        return True if len(parts) >= 3 and parts[1] in {"images", "thumbs"} else False

    if parts[0] == "cbz":
        return True

    if len(parts) >= 3 and parts[1] in {"pages", "thumbs", "downloads"}:
        return True

    return False


def _build_http_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _list_directory(
    *,
    session: requests.Session,
    storage_api_base_url: str,
    storage_zone: str,
    read_api_key: str,
    timeout_seconds: float,
    prefix: str,
) -> list[dict[str, object]]:
    normalized_prefix = prefix.strip().strip("/")
    object_path = f"static/{normalized_prefix}/" if normalized_prefix else "static/"
    encoded_path = quote(object_path, safe="/")
    url = f"{storage_api_base_url.rstrip('/')}/{storage_zone}/{encoded_path}"

    response = session.get(
        url,
        headers={"AccessKey": read_api_key, "Accept": "application/json"},
        timeout=timeout_seconds,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        return []

    payload_items = cast(list[object], payload)
    normalized_items: list[dict[str, object]] = []
    for item in payload_items:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[object, object], item)
        normalized_items.append({str(k): v for k, v in typed_item.items()})
    return normalized_items


def _list_all_static_keys(
    *,
    session: requests.Session,
    storage_api_base_url: str,
    storage_zone: str,
    read_api_key: str,
    timeout_seconds: float,
) -> set[str]:
    keys: set[str] = set()
    queue: list[str] = [""]
    visited: set[str] = set()

    while queue:
        prefix = queue.pop()
        if prefix in visited:
            continue
        visited.add(prefix)

        try:
            items = _list_directory(
                session=session,
                storage_api_base_url=storage_api_base_url,
                storage_zone=storage_zone,
                read_api_key=read_api_key,
                timeout_seconds=timeout_seconds,
                prefix=prefix,
            )
        except Exception as exc:
            print(f"WARN failed to list prefix={prefix}: {exc}", file=sys.stderr)
            continue

        for item in items:
            name = str(item.get("ObjectName", "")).strip().strip("/")
            if not name:
                continue

            is_directory_obj = item.get("IsDirectory", False)
            is_directory = bool(is_directory_obj)
            child_prefix = f"{prefix}/{name}".strip("/") if prefix else name

            if is_directory:
                queue.append(child_prefix)
                continue

            keys.add(child_prefix)

    return keys


def _cbz_candidates_for_work(work_id: str, cbz_path_text: str) -> set[str]:
    keys: set[str] = set()
    normalized_work_id = work_id.strip()
    normalized_cbz_path = cbz_path_text.strip()
    if not normalized_cbz_path:
        return keys

    if normalized_cbz_path.startswith("http://") or normalized_cbz_path.startswith(
        "https://"
    ):
        parsed_path = urlsplit(normalized_cbz_path).path
    else:
        parsed_path = normalized_cbz_path

    static_tail = ""
    if "/static/" in parsed_path:
        static_tail = parsed_path.split("/static/", 1)[1].strip("/")
    elif parsed_path.startswith("static/"):
        static_tail = parsed_path[len("static/") :].strip("/")

    if static_tail:
        keys.add(static_tail)
        if static_tail.endswith(".cbz"):
            keys.add(f"{static_tail}.meta.json")

    cbz_filename = Path(parsed_path).name.strip()
    if cbz_filename:
        encoded_name = quote(cbz_filename, safe="")
        for filename in {cbz_filename, encoded_name}:
            keys.add(f"cbz/{filename}")
            keys.add(f"cbz/{filename}.meta.json")
            if normalized_work_id:
                encoded_work_id = quote(normalized_work_id, safe="")
                keys.add(f"{encoded_work_id}/downloads/{filename}")

    return keys


def _expected_media_keys_from_db() -> set[str]:
    keys: set[str] = set()

    with get_connection() as connection:
        page_rows = connection.execute(
            """
            SELECT work_id, image_filename, thumb_filename
            FROM pages
            """
        ).fetchall()

        work_rows = connection.execute(
            """
            SELECT id, cbz_path
            FROM works
            """
        ).fetchall()

        fanart_rows = connection.execute(
            """
            SELECT image_filename, thumb_filename
            FROM fanart_items
            """
        ).fetchall()

    for row in page_rows:
        work_id = str(row["work_id"]).strip()
        image_name = str(row["image_filename"]).strip().lstrip("/")
        thumb_obj = row["thumb_filename"]
        thumb_name = str(thumb_obj).strip().lstrip("/") if thumb_obj is not None else ""

        if work_id and image_name:
            encoded_work_id = quote(work_id, safe="")
            encoded_image = quote(image_name, safe="/")
            keys.add(f"{encoded_work_id}/pages/{encoded_image}")

        if work_id and thumb_name:
            encoded_work_id = quote(work_id, safe="")
            encoded_thumb = quote(thumb_name, safe="/")
            keys.add(f"{encoded_work_id}/thumbs/{encoded_thumb}")

    for row in work_rows:
        work_id = str(row["id"]).strip()
        cbz_path_obj = row["cbz_path"]
        cbz_path = str(cbz_path_obj).strip() if cbz_path_obj is not None else ""
        keys.update(_cbz_candidates_for_work(work_id, cbz_path))

    for row in fanart_rows:
        image_name = str(row["image_filename"]).strip().lstrip("/")
        thumb_obj = row["thumb_filename"]
        thumb_name = str(thumb_obj).strip().lstrip("/") if thumb_obj is not None else ""

        if image_name:
            keys.add(f"fanart/images/{quote(image_name, safe='/')}")
        if thumb_name:
            keys.add(f"fanart/thumbs/{quote(thumb_name, safe='/')}")

    return {key for key in keys if _is_media_candidate_key(key)}


def _delete_key(
    *,
    session: requests.Session,
    storage_api_base_url: str,
    storage_zone: str,
    write_api_key: str,
    timeout_seconds: float,
    key: str,
) -> None:
    encoded_path = quote(f"static/{key}", safe="/")
    url = f"{storage_api_base_url.rstrip('/')}/{storage_zone}/{encoded_path}"
    response = session.delete(
        url,
        headers={"AccessKey": write_api_key, "Accept": "application/json"},
        timeout=timeout_seconds,
    )
    if response.status_code in {200, 204, 404}:
        return
    response.raise_for_status()


def cleanup_orphans(
    *,
    dry_run: bool,
    limit: int,
    storage_api_base_url: str,
) -> int:
    settings = get_settings()
    read_key = settings.media_bunny_api_key_ro.strip()
    write_key = settings.media_bunny_api_key_rw.strip()
    storage_zone = settings.media_bunny_storage_zone.strip()
    timeout_seconds = settings.media_bunny_timeout_seconds

    if not read_key:
        raise RuntimeError(
            "media_bunny_api_key_ro is empty; cannot list remote objects"
        )
    if not storage_zone:
        raise RuntimeError(
            "media_bunny_storage_zone is empty; cannot list remote objects"
        )
    if not dry_run and not write_key:
        raise RuntimeError(
            "media_bunny_api_key_rw is empty; cannot delete remote objects"
        )

    session = _build_http_session()
    stats = CleanupStats()

    remote_keys = _list_all_static_keys(
        session=session,
        storage_api_base_url=storage_api_base_url,
        storage_zone=storage_zone,
        read_api_key=read_key,
        timeout_seconds=timeout_seconds,
    )
    candidate_remote_keys = {key for key in remote_keys if _is_media_candidate_key(key)}

    expected_keys = _expected_media_keys_from_db()
    orphaned_keys = sorted(candidate_remote_keys - expected_keys)

    if limit > 0:
        orphaned_keys = orphaned_keys[:limit]

    stats.remote_scanned = len(candidate_remote_keys)
    stats.expected = len(expected_keys)
    stats.orphaned = len(orphaned_keys)

    print("Bunny orphan cleanup plan")
    print(f"  candidate_remote_keys: {stats.remote_scanned}")
    print(f"  expected_db_keys: {stats.expected}")
    print(f"  orphaned_keys: {stats.orphaned}")
    if dry_run:
        print("  mode: dry-run")
    else:
        print("  mode: delete")

    preview = orphaned_keys[:50]
    for key in preview:
        print(f"ORPHAN {key}")
    if len(orphaned_keys) > len(preview):
        print(
            f"... {len(orphaned_keys) - len(preview)} more orphan keys omitted from preview"
        )

    if dry_run:
        return 0

    for index, key in enumerate(orphaned_keys, start=1):
        try:
            _delete_key(
                session=session,
                storage_api_base_url=storage_api_base_url,
                storage_zone=storage_zone,
                write_api_key=write_key,
                timeout_seconds=timeout_seconds,
                key=key,
            )
            stats.deleted += 1
            if index % 100 == 0:
                print(f"deleted {stats.deleted}/{stats.orphaned}")
        except Exception as exc:
            stats.failed += 1
            print(f"ERROR deleting key={key}: {exc}", file=sys.stderr)

    print("Cleanup summary")
    print(f"  deleted: {stats.deleted}")
    print(f"  failed: {stats.failed}")
    return 1 if stats.failed > 0 else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and optionally delete orphaned Bunny media keys not referenced by FANIC DB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview orphan keys without deleting (default behavior)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete detected orphan keys (default is dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of orphan keys to process (0 means all)",
    )
    parser.add_argument(
        "--storage-api-base-url",
        default="https://ny.storage.bunnycdn.com",
        help=(
            "Bunny Storage API base URL. "
            "Use a regional endpoint when needed, for example "
            "https://ny.storage.bunnycdn.com"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if bool(args.delete) and bool(args.dry_run):
        raise SystemExit("Use either --delete or --dry-run, not both")

    dry_run = True if bool(args.dry_run) else not bool(args.delete)
    return cleanup_orphans(
        dry_run=dry_run,
        limit=int(args.limit),
        storage_api_base_url=str(args.storage_api_base_url).strip(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
