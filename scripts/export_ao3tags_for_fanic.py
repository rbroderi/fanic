#!/usr/bin/env python3
"""Convert AO3 tag CSV dumps into Fanic-ready JSON and SQL.

Default source expects a CSV dump like:
  tmp/ao3tags-live/tags-20210226.csv

The script maps AO3 tag classes to Fanic tag types, filters by count/canonical,
and writes:
1) normalized JSON for review
2) SQL upserts for Fanic's tags table
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path

from fanic.utils import slugify

AO3_TO_FANIC_TYPE = {
    "Freeform": "freeform",
    "Fandom": "fandom",
    "Relationship": "relationship",
    "Character": "character",
    "Rating": "rating",
    "ArchiveWarning": "archive_warning",
    "Category": "category",
}

DEFAULT_INCLUDED_TYPES = [
    "freeform",
    "fandom",
    "relationship",
    "character",
    "rating",
    "archive_warning",
    "category",
]


@dataclass(frozen=True)
class CanonicalTag:
    slug: str
    name: str
    type: str
    ao3_count: int
    ao3_type: str


def _to_int(value: str) -> int:
    stripped = value.strip()
    if not stripped:
        return 0
    try:
        return int(stripped)
    except ValueError:
        return 0


def _sql_quote(value: str) -> str:
    return value.replace("'", "''")


def _parse_include_types(raw: str) -> set[str]:
    selected = {part.strip() for part in raw.split(",") if part.strip()}
    if selected:
        return selected
    return set(DEFAULT_INCLUDED_TYPES)


def _load_tags_from_csv(
    source_path: Path,
    *,
    min_count: int,
    include_types: set[str],
    canonical_only: bool,
) -> tuple[list[CanonicalTag], dict[str, int]]:
    by_slug: dict[str, CanonicalTag] = {}
    stats = {
        "rows_total": 0,
        "rows_unmapped_type": 0,
        "rows_excluded_type": 0,
        "rows_non_canonical": 0,
        "rows_below_min_count": 0,
        "rows_empty_name": 0,
        "rows_kept": 0,
    }

    with source_path.open("r", encoding="utf-8", newline="") as source_file:
        reader = csv.DictReader(source_file)
        for row in reader:
            stats["rows_total"] += 1
            if stats["rows_total"] % 200000 == 0:
                print(f"Processed {stats['rows_total']} rows...")

            ao3_type = (row.get("type") if row.get("type") else "").strip()
            fanic_type = AO3_TO_FANIC_TYPE.get(ao3_type)
            if not fanic_type:
                stats["rows_unmapped_type"] += 1
                continue
            if fanic_type not in include_types:
                stats["rows_excluded_type"] += 1
                continue

            canonical_text = (row.get("canonical") if row.get("canonical") else "").strip().lower()
            is_canonical = canonical_text == "true"
            if canonical_only and not is_canonical:
                stats["rows_non_canonical"] += 1
                continue

            count = _to_int(row.get("cached_count") if row.get("cached_count") else "")
            if count < min_count:
                stats["rows_below_min_count"] += 1
                continue

            name = (row.get("name") if row.get("name") else "").strip()
            if not name:
                stats["rows_empty_name"] += 1
                continue

            tag_slug = slugify(name)
            candidate = CanonicalTag(
                slug=tag_slug,
                name=name,
                type=fanic_type,
                ao3_count=count,
                ao3_type=ao3_type,
            )
            existing = by_slug.get(tag_slug)
            if not existing:
                by_slug[tag_slug] = candidate
                stats["rows_kept"] += 1
                continue
            if candidate.ao3_count > existing.ao3_count:
                by_slug[tag_slug] = candidate
                continue
            if candidate.ao3_count == existing.ao3_count and len(candidate.name) > len(existing.name):
                by_slug[tag_slug] = candidate

    tags = sorted(by_slug.values(), key=lambda item: item.slug)
    return tags, stats


def _write_json(
    output_path: Path,
    *,
    source_path: Path,
    min_count: int,
    include_types: set[str],
    canonical_only: bool,
    tags: list[CanonicalTag],
    stats: dict[str, int],
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(source_path),
        "source_format": "ao3_csv_dump",
        "canonical_only": canonical_only,
        "min_count": min_count,
        "include_types": sorted(include_types),
        "stats": stats,
        "exported_entries": len(tags),
        "tags": [
            {
                "slug": tag.slug,
                "name": tag.name,
                "type": tag.type,
                "ao3_count": tag.ao3_count,
                "ao3_type": tag.ao3_type,
            }
            for tag in tags
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_sql(output_path: Path, tags: list[CanonicalTag]) -> None:
    lines = ["BEGIN;", ""]
    for tag in tags:
        slug_sql = _sql_quote(tag.slug)
        name_sql = _sql_quote(tag.name)
        type_sql = _sql_quote(tag.type)
        seed_count_sql = str(tag.ao3_count)
        lines.append(
            "INSERT INTO tags (slug, name, type) VALUES "
            f"('{slug_sql}', '{name_sql}', '{type_sql}') "
            "ON CONFLICT(slug) DO UPDATE SET "
            "name = excluded.name, type = excluded.type;"
        )
        lines.append(
            "INSERT INTO tag_popularity (tag_id, seed_count, usage_count) "
            "SELECT id, "
            f"{seed_count_sql}, 0 "
            "FROM tags WHERE slug = "
            f"'{slug_sql}' "
            "ON CONFLICT(tag_id) DO UPDATE SET "
            "seed_count = CASE "
            "WHEN excluded.seed_count > tag_popularity.seed_count "
            "THEN excluded.seed_count "
            "ELSE tag_popularity.seed_count "
            "END, "
            "updated_at = CURRENT_TIMESTAMP;"
        )
    lines.extend(["", "COMMIT;", ""])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert AO3 tag CSV dumps into Fanic-ready JSON + SQL outputs")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("tmp/ao3tags-live/tags-20210226.csv"),
        help="Path to AO3 CSV dump (default: tmp/ao3tags-live/tags-20210226.csv)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("logs"),
        help="Output directory for generated files (default: logs)",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Only keep tags with cached_count >= this value (default: 1)",
    )
    parser.add_argument(
        "--include-types",
        default=",".join(DEFAULT_INCLUDED_TYPES),
        help=(
            "Comma-separated Fanic types to include. "
            "Default: freeform,fandom,relationship,character,rating,archive_warning,category"
        ),
    )
    parser.add_argument(
        "--include-non-canonical",
        action="store_true",
        help="Include rows where canonical is false (default excludes them)",
    )
    parser.add_argument(
        "--json-name",
        default="ao3_tags_dump.fanic.json",
        help="Output JSON filename (default: ao3_tags_dump.fanic.json)",
    )
    parser.add_argument(
        "--sql-name",
        default="ao3_tags_dump.fanic.upsert.sql",
        help="Output SQL filename (default: ao3_tags_dump.fanic.upsert.sql)",
    )

    args = parser.parse_args()

    source_path = args.source.expanduser().resolve()
    if not source_path.exists():
        raise RuntimeError(f"Source CSV not found: {source_path}")

    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    min_count = args.min_count if args.min_count >= 0 else 0
    include_types = _parse_include_types(args.include_types)
    canonical_only = False if args.include_non_canonical else True

    tags, stats = _load_tags_from_csv(
        source_path,
        min_count=min_count,
        include_types=include_types,
        canonical_only=canonical_only,
    )

    json_path = out_dir / args.json_name
    sql_path = out_dir / args.sql_name
    _write_json(
        json_path,
        source_path=source_path,
        min_count=min_count,
        include_types=include_types,
        canonical_only=canonical_only,
        tags=tags,
        stats=stats,
    )
    _write_sql(sql_path, tags)

    print(f"Exported {len(tags)} tags")
    print(f"JSON: {json_path}")
    print(f"SQL:  {sql_path}")
    print("Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
