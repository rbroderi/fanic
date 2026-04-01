#!/usr/bin/env python3
"""Export AO3 freeform tags into Fanic-friendly seed files.

This script consumes the ceejbot/ao3tags dataset (tags.json), which contains
canonical AO3 freeform tags and usage counts, then writes:
1) a normalized JSON payload for review/versioning
2) a SQLite upsert SQL file suitable for Fanic's tags table

Usage examples:
  python scripts/export_ao3tags_for_fanic.py
  python scripts/export_ao3tags_for_fanic.py --min-count 50
  python scripts/export_ao3tags_for_fanic.py --source ./tags.json --out-dir ./tmp
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

from alive_progress import alive_bar

from fanic.utils import slugify

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


AO3_TAGS_RAW_URLS = [
    "https://raw.githubusercontent.com/ceejbot/ao3tags/master/tags.json",
    "https://raw.githubusercontent.com/ceejbot/ao3tags/main/tags.json",
]
AO3TAGS_GIT_URL = "https://github.com/ceejbot/ao3tags.git"
AO3_FREEFORM_SEARCH_PAGE_1_URL = (
    "https://archiveofourown.org/tags/search?page=1"
    "&query%5Bcanonical%5D=true"
    "&query%5Bname%5D="
    "&query%5Btype%5D=Freeform"
    "&utf8=%E2%9C%93"
)


def _ao3_freeform_search_url(page: int) -> str:
    return (
        "https://archiveofourown.org/tags/search"
        f"?page={page}"
        "&query%5Bcanonical%5D=true"
        "&query%5Bname%5D="
        "&query%5Btype%5D=Freeform"
        "&utf8=%E2%9C%93"
    )


@dataclass(frozen=True)
class CanonicalTag:
    slug: str
    name: str
    type: str
    ao3_count: int


def _read_json_from_url(url: str, *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "fanic-ao3-tag-exporter/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read().decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Expected top-level JSON object from AO3 tags source")
    return parsed


def _read_text_from_url(
    url: str,
    *,
    timeout_seconds: float = 20.0,
    headers: dict[str, str] | None = None,
) -> str:
    request_headers = (
        headers
        if headers
        else {
            "User-Agent": "fanic-ao3-tag-exporter/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml",
        }
    )
    request = Request(
        url,
        headers=request_headers,
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_max_page_from_ao3_search_html(html: str) -> int:
    page_numbers = [
        int(match) for match in re.findall(r"/tags/search\?[^\"\s>]*page=(\d+)", html)
    ]
    if not page_numbers:
        return 1
    return max(page_numbers)


def _is_ao3_bot_challenge_html(html: str) -> bool:
    lowered = html.lower()
    return (
        "shields are up" in lowered
        or "challenge-platform" in lowered
        or "__cf_chl" in lowered
        or "enable javascript and cookies to continue" in lowered
    )


def _assert_not_ao3_bot_challenge_html(html: str) -> None:
    if _is_ao3_bot_challenge_html(html):
        raise RuntimeError(
            "AO3 returned a bot-protection challenge page instead of tag results. "
            "Live AO3 fetching cannot continue from this environment. "
            "For interactive mode, copy the full browser Cookie header and exact "
            "browser User-Agent (not only cf_clearance), or use --source with a "
            "previously generated tags.json."
        )


def _detect_ao3_freeform_page_count() -> int:
    with alive_bar(2, title="Detecting AO3 page count", force_tty=True) as bar:
        html = _read_text_from_url(AO3_FREEFORM_SEARCH_PAGE_1_URL)
        bar()
        _assert_not_ao3_bot_challenge_html(html)
        max_page = _extract_max_page_from_ao3_search_html(html)
        bar()
    return max_page if max_page > 0 else 1


def _detect_ao3_freeform_page_count_with_headers(headers: dict[str, str]) -> int:
    with alive_bar(2, title="Detecting AO3 page count", force_tty=True) as bar:
        html = _read_text_from_url(AO3_FREEFORM_SEARCH_PAGE_1_URL, headers=headers)
        bar()
        _assert_not_ao3_bot_challenge_html(html)
        max_page = _extract_max_page_from_ao3_search_html(html)
        bar()
    return max_page if max_page > 0 else 1


def _read_json_from_known_urls() -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    for url in AO3_TAGS_RAW_URLS:
        try:
            return _read_json_from_url(url), url
        except (ValueError, OSError, URLError) as exc:
            errors.append(f"{url} -> {exc}")
    raise RuntimeError("Unable to download AO3 tags JSON:\n" + "\n".join(errors))


def _read_json_from_file(path: Path) -> dict[str, Any]:
    payload = path.read_text(encoding="utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Expected top-level JSON object from AO3 tags file")
    return parsed


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = True,
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=capture_output,
        text=True,
    )
    if completed.returncode == 0:
        return
    if capture_output:
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        details = "\n".join(part for part in [stdout, stderr] if part)
        raise RuntimeError(f"Command failed in {cwd}: {' '.join(command)}\n{details}")
    raise RuntimeError(f"Command failed in {cwd}: {' '.join(command)}")


def _patch_fetchtags_page_count(fetchtags_path: Path, page_count: int) -> None:
    source = fetchtags_path.read_text(encoding="utf-8")
    patched, replaced = re.subn(
        r"var\s+total\s*=\s*\d+;",
        f"var total = {page_count};",
        source,
        count=1,
    )
    if replaced == 0:
        raise RuntimeError("Unable to locate page count line in fetchtags.js")
    fetchtags_path.write_text(patched, encoding="utf-8")


def _prepare_ao3tags_repo(repo_path: Path, *, page_count: int) -> Path:
    if not repo_path.exists():
        _run_command(
            ["git", "clone", AO3TAGS_GIT_URL, str(repo_path)], cwd=repo_path.parent
        )

    fetchtags_path = repo_path / "fetchtags.js"
    parsepages_path = repo_path / "parsepages.js"
    if not fetchtags_path.exists() or not parsepages_path.exists():
        raise RuntimeError(f"Invalid ao3tags checkout at {repo_path}")

    _run_command(["npm", "install"], cwd=repo_path)
    _patch_fetchtags_page_count(fetchtags_path, page_count)
    return repo_path


def _prepare_ao3tags_repo_for_parser(repo_path: Path) -> Path:
    if not repo_path.exists():
        _run_command(
            ["git", "clone", AO3TAGS_GIT_URL, str(repo_path)],
            cwd=repo_path.parent,
        )

    parsepages_path = repo_path / "parsepages.js"
    if not parsepages_path.exists():
        raise RuntimeError(f"Invalid ao3tags checkout at {repo_path}")

    _run_command(["npm", "install"], cwd=repo_path)
    return repo_path


def _ao3_headers_from_auth_inputs(
    cookie_header: str,
    cf_clearance: str,
    user_agent: str,
) -> dict[str, str]:
    normalized_cookie_header = cookie_header.strip()
    normalized_cf_clearance = cf_clearance.strip()
    cookie_value = (
        normalized_cookie_header
        if normalized_cookie_header
        else f"cf_clearance={normalized_cf_clearance}"
    )
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml",
        "Cookie": cookie_value,
    }


def _prompt_for_cookie_header_or_cf_clearance() -> tuple[str, str]:
    print(
        "\nManual browser auth required.\n"
        "1) Open this URL in your local browser:\n"
        f"   {AO3_FREEFORM_SEARCH_PAGE_1_URL}\n"
        "2) Complete the anti-bot challenge.\n"
        "3) In browser devtools, copy the full Cookie request header for that page.\n"
        "   (Fallback: copy only cf_clearance value.)\n"
    )
    cookie_header = input("Paste full Cookie header (or press Enter to skip): ").strip()
    if cookie_header:
        return cookie_header, ""
    token = input("Paste cf_clearance cookie value: ").strip()
    if not token:
        raise RuntimeError("Either Cookie header or cf_clearance value is required")
    return "", token


def _reset_ao3_input_dir(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    for old_page in input_dir.glob("page*.html"):
        old_page.unlink()


def _download_ao3_pages_with_headers(
    *,
    repo_path: Path,
    page_count: int,
    headers: dict[str, str],
) -> None:
    input_dir = repo_path / "input"
    _reset_ao3_input_dir(input_dir)

    with alive_bar(page_count, title="Downloading AO3 pages", force_tty=True) as bar:
        for page in range(1, page_count + 1):
            html = _read_text_from_url(_ao3_freeform_search_url(page), headers=headers)
            _assert_not_ao3_bot_challenge_html(html)
            page_path = input_dir / f"page{page:03d}.html"
            page_path.write_text(html, encoding="utf-8")
            bar()


def _read_json_via_interactive_browser_auth(
    *,
    page_count: int,
    page_count_auto: bool,
    repo_dir: Path | None,
    cookie_header: str | None,
    cf_clearance: str | None,
    user_agent: str,
) -> tuple[dict[str, Any], str]:
    provided_cookie_header = cookie_header.strip() if cookie_header else ""
    clearance_token = cf_clearance.strip() if cf_clearance else ""
    if not provided_cookie_header and not clearance_token:
        provided_cookie_header, clearance_token = (
            _prompt_for_cookie_header_or_cf_clearance()
        )

    headers = _ao3_headers_from_auth_inputs(
        provided_cookie_header,
        clearance_token,
        user_agent,
    )
    resolved_page_count = (
        _detect_ao3_freeform_page_count_with_headers(headers)
        if page_count_auto
        else page_count
    )

    if resolved_page_count <= 0:
        raise RuntimeError("Resolved AO3 page count must be greater than zero")

    if repo_dir is not None:
        prepared_repo = _prepare_ao3tags_repo_for_parser(repo_dir)
        _download_ao3_pages_with_headers(
            repo_path=prepared_repo,
            page_count=resolved_page_count,
            headers=headers,
        )
        _run_command(["node", "parsepages.js"], cwd=prepared_repo, capture_output=False)
        tags_path = prepared_repo / "tags.json"
        return _read_json_from_file(
            tags_path
        ), f"interactive AO3 via repo at {prepared_repo}"

    with tempfile.TemporaryDirectory(prefix="fanic-ao3tags-") as tmpdir:
        prepared_repo = _prepare_ao3tags_repo_for_parser(Path(tmpdir) / "ao3tags")
        _download_ao3_pages_with_headers(
            repo_path=prepared_repo,
            page_count=resolved_page_count,
            headers=headers,
        )
        _run_command(["node", "parsepages.js"], cwd=prepared_repo, capture_output=False)
        tags_path = prepared_repo / "tags.json"
        source = f"interactive AO3 via temporary ao3tags checkout ({prepared_repo})"
        return _read_json_from_file(tags_path), source


def _read_json_via_ao3tags_live_fetch(
    *,
    page_count: int,
    repo_dir: Path | None,
) -> tuple[dict[str, Any], str]:
    if page_count <= 0:
        raise ValueError("--ao3tags-page-count must be greater than 0")

    def _verify_fetched_page(repo_path: Path) -> None:
        page_1_path = repo_path / "input" / "page001.html"
        if not page_1_path.exists():
            raise RuntimeError(
                "ao3tags fetch completed but input/page001.html was not found"
            )
        page_1_html = page_1_path.read_text(encoding="utf-8", errors="replace")
        _assert_not_ao3_bot_challenge_html(page_1_html)

    if repo_dir is not None:
        with alive_bar(4, title="Refreshing AO3 tags", force_tty=True) as bar:
            prepared_repo = _prepare_ao3tags_repo(repo_dir, page_count=page_count)
            bar()
            _run_command(
                ["node", "fetchtags.js"],
                cwd=prepared_repo,
                capture_output=False,
            )
            bar()
            _verify_fetched_page(prepared_repo)
            _run_command(
                ["node", "parsepages.js"],
                cwd=prepared_repo,
                capture_output=False,
            )
            bar()
            tags_path = prepared_repo / "tags.json"
            source_data = _read_json_from_file(tags_path)
            bar()
        return source_data, f"live AO3 via ao3tags repo at {prepared_repo}"

    with tempfile.TemporaryDirectory(prefix="fanic-ao3tags-") as tmpdir:
        with alive_bar(4, title="Refreshing AO3 tags", force_tty=True) as bar:
            prepared_repo = _prepare_ao3tags_repo(
                Path(tmpdir) / "ao3tags",
                page_count=page_count,
            )
            bar()
            _run_command(
                ["node", "fetchtags.js"],
                cwd=prepared_repo,
                capture_output=False,
            )
            bar()
            _verify_fetched_page(prepared_repo)
            _run_command(
                ["node", "parsepages.js"],
                cwd=prepared_repo,
                capture_output=False,
            )
            bar()
            tags_path = prepared_repo / "tags.json"
            source_data = _read_json_from_file(tags_path)
            bar()
        source = f"live AO3 via temporary ao3tags checkout ({prepared_repo})"
        return source_data, source


def _to_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            return int(stripped)
        except ValueError:
            return 0
    return 0


def _build_canonical_tags(
    source: dict[str, Any], *, min_count: int
) -> list[CanonicalTag]:
    by_slug: dict[str, CanonicalTag] = {}
    with alive_bar(len(source), title="Normalizing tags", force_tty=True) as bar:
        for raw_name, raw_count in source.items():
            bar()
            name = raw_name.strip()
            if not name:
                continue
            count = _to_int(raw_count)
            if count < min_count:
                continue

            tag_slug = slugify(name)
            candidate = CanonicalTag(
                slug=tag_slug,
                name=name,
                type="freeform",
                ao3_count=count,
            )
            existing = by_slug.get(tag_slug)
            if not existing:
                by_slug[tag_slug] = candidate
                continue
            if candidate.ao3_count > existing.ao3_count:
                by_slug[tag_slug] = candidate
                continue
            if candidate.ao3_count == existing.ao3_count and len(candidate.name) > len(
                existing.name
            ):
                by_slug[tag_slug] = candidate

    return sorted(by_slug.values(), key=lambda tag: tag.slug)


def _sql_quote(value: str) -> str:
    return value.replace("'", "''")


def _write_sql(path: Path, tags: list[CanonicalTag]) -> None:
    lines: list[str] = ["BEGIN;", ""]
    with alive_bar(len(tags), title="Writing SQL", force_tty=True) as bar:
        for tag in tags:
            bar()
            slug_sql = _sql_quote(tag.slug)
            name_sql = _sql_quote(tag.name)
            lines.append(
                "INSERT INTO tags (slug, name, type) VALUES "
                f"('{slug_sql}', '{name_sql}', 'freeform') "
                "ON CONFLICT(slug) DO UPDATE SET "
                "name = excluded.name, type = excluded.type "
                "WHERE tags.type = 'freeform';"
            )
    lines.extend(["", "COMMIT;", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_json(
    path: Path,
    *,
    source_description: str,
    min_count: int,
    source_size: int,
    tags: list[CanonicalTag],
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": source_description,
        "notes": [
            "Derived from ceejbot/ao3tags tags.json.",
            "Dataset contains AO3 canonical freeform tags, not all AO3 tag types.",
        ],
        "tag_type": "freeform",
        "min_count": min_count,
        "source_entries": source_size,
        "exported_entries": len(tags),
        "tags": [
            {
                "slug": tag.slug,
                "name": tag.name,
                "type": tag.type,
                "ao3_count": tag.ao3_count,
            }
            for tag in tags
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch or read ceejbot/ao3tags tags.json and export "
            "Fanic-ready freeform tag seed files."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        help=(
            "Path to a local tags.json file from ceejbot/ao3tags. "
            "If omitted, the script downloads the latest file from GitHub."
        ),
    )
    parser.add_argument(
        "--refresh-from-ao3",
        action="store_true",
        help=(
            "Run ceejbot/ao3tags fetchtags.js + parsepages.js to build a live "
            "tags.json from AO3 before export."
        ),
    )
    parser.add_argument(
        "--ao3tags-repo-dir",
        type=Path,
        help=(
            "Path to a local ao3tags checkout to reuse. If missing, it will be "
            "cloned there. If omitted, a temporary checkout is used."
        ),
    )
    parser.add_argument(
        "--ao3tags-page-count",
        type=int,
        default=1000,
        help=(
            "Number of AO3 search result pages to fetch in live mode (default: 1000)."
        ),
    )
    parser.add_argument(
        "--ao3tags-page-count-auto",
        action="store_true",
        help=(
            "Auto-detect current AO3 freeform tag page count from page 1 "
            "pagination and use that value."
        ),
    )
    parser.add_argument(
        "--interactive-browser-auth",
        action="store_true",
        help=(
            "Use manual browser-auth flow for remote SSH: solve AO3 challenge in "
            "local browser, then paste cf_clearance cookie for scripted download."
        ),
    )
    parser.add_argument(
        "--ao3-cookie-header",
        default="",
        help=(
            "Full Cookie header copied from a successful AO3 browser request. "
            "Preferred for remote SSH interactive mode."
        ),
    )
    parser.add_argument(
        "--cf-clearance",
        default="",
        help=(
            "Optional cf_clearance cookie value. Use --ao3-cookie-header when "
            "possible for better challenge compatibility."
        ),
    )
    parser.add_argument(
        "--ao3-user-agent",
        default=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        help="User-Agent header used in interactive browser-auth mode.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "logs",
        help="Output directory for generated files (default: logs).",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Only keep tags with usage count >= this value (default: 1).",
    )
    parser.add_argument(
        "--json-name",
        default="ao3_freeform_tags.fanic.json",
        help="Output JSON filename (default: ao3_freeform_tags.fanic.json).",
    )
    parser.add_argument(
        "--sql-name",
        default="ao3_freeform_tags.fanic.upsert.sql",
        help="Output SQL filename (default: ao3_freeform_tags.fanic.upsert.sql).",
    )

    args = parser.parse_args()

    min_count = args.min_count if args.min_count >= 0 else 0
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.refresh_from_ao3:
        live_repo_dir = (
            args.ao3tags_repo_dir.expanduser().resolve()
            if args.ao3tags_repo_dir
            else None
        )
        if live_repo_dir and not live_repo_dir.parent.exists():
            live_repo_dir.parent.mkdir(parents=True, exist_ok=True)
        if args.interactive_browser_auth:
            source_data, source_description = _read_json_via_interactive_browser_auth(
                page_count=args.ao3tags_page_count,
                page_count_auto=args.ao3tags_page_count_auto,
                repo_dir=live_repo_dir,
                cookie_header=args.ao3_cookie_header,
                cf_clearance=args.cf_clearance,
                user_agent=args.ao3_user_agent,
            )
        else:
            resolved_page_count = (
                _detect_ao3_freeform_page_count()
                if args.ao3tags_page_count_auto
                else args.ao3tags_page_count
            )
            print(f"Using AO3 page count: {resolved_page_count}")
            source_data, source_description = _read_json_via_ao3tags_live_fetch(
                page_count=resolved_page_count,
                repo_dir=live_repo_dir,
            )
    elif args.source:
        source_path = args.source.expanduser().resolve()
        source_data = _read_json_from_file(source_path)
        source_description = str(source_path)
    else:
        source_data, source_description = _read_json_from_known_urls()

    tags = _build_canonical_tags(source_data, min_count=min_count)

    json_path = out_dir / args.json_name
    sql_path = out_dir / args.sql_name

    _write_json(
        json_path,
        source_description=source_description,
        min_count=min_count,
        source_size=len(source_data),
        tags=tags,
    )
    _write_sql(sql_path, tags)

    print(f"Wrote {len(tags)} tags")
    print(f"JSON: {json_path}")
    print(f"SQL:  {sql_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
