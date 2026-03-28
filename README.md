# FANIC: Fan Archive Nexus for Illustrated Comics

[![Ruff](https://github.com/rbroderi/fanic/actions/workflows/ruff.yml/badge.svg)](https://github.com/rbroderi/fanic/actions/workflows/ruff.yml)
[![autopep695](https://github.com/rbroderi/fanic/actions/workflows/autopep695.yml/badge.svg)](https://github.com/rbroderi/fanic/actions/workflows/autopep695.yml)
[![pyupgrade](https://github.com/rbroderi/fanic/actions/workflows/pyupgrade.yml/badge.svg)](https://github.com/rbroderi/fanic/actions/workflows/pyupgrade.yml)
[![ComicInfo XSD](https://github.com/rbroderi/fanic/actions/workflows/comicinfo-xsd.yml/badge.svg)](https://github.com/rbroderi/fanic/actions/workflows/comicinfo-xsd.yml)

FANIC is a self-hosted web archive for fan-made comics and illustrations. Upload CBZ archives, browse works with rich tagging, read in the browser with keyboard navigation and saved progress, and share fanart — all backed by AI-powered content moderation.

The project is built on [Cylinder](https://github.com/rbroderi/cylinder) (a file-based WSGI routing framework), SQLite, and OpenCLIP for moderation. During the current **alpha trial** period, access can be gated behind invite codes.

### Highlights

- **Comic reader** — keyboard page-flip, sidebar thumbnails, bookmarks, and per-user reading progress.
- **CBZ ingest pipeline** — extract pages from CBZ archives, auto-generate AVIF thumbnails, parse `ComicInfo.xml` or JSON metadata.
- **Structured tagging** — fandom, character, relationship, and freeform tags with synonym canonicalization.
- **Fanart gallery** — community-uploaded illustrations with content-addressed storage.
- **AI moderation** — OpenCLIP-based style classifier (blocks photorealistic uploads) and NSFW detector with configurable thresholds.
- **User system** — profiles, bookmarks, notifications (kudos/comments), reading history.
- **Admin dashboard** — user management, role-based access, DMCA/feedback report tracking.
- **Backup & restore** — full ZIP export of database + media with pre-restore safety snapshots.

## Examples

- Comic metadata sample: [examples/ComicInfo.xml](examples/ComicInfo.xml)
- Theme sample: [examples/theme_example.toml](examples/theme_example.toml)

## Quick Start

1. Create environment and sync dependencies.

```powershell
uv venv
uv sync
```

2. Initialize the database.

```powershell
uv run fanic init-db
```

3. Ingest a CBZ.

```powershell
uv run fanic ingest C:\path\to\comic.cbz --metadata C:\path\to\metadata.json
```

Optional one-off: convert existing thumbnails to AVIF.

```powershell
uv run fanic convert-thumbs-avif --dry-run
uv run fanic convert-thumbs-avif
```

4. Run the site.

```powershell
uv run fanic serve --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `fanic init-db` | Initialize the SQLite schema and storage directories |
| `fanic ingest <cbz>` | Ingest a CBZ archive (optional `--metadata` JSON) |
| `fanic serve` | Run the local WSGI server (`--host`, `--port`) |
| `fanic convert-thumbs-avif` | Batch-convert page thumbnails to AVIF (`--dry-run` supported) |
| `fanic hash-admin-password` | Generate a PBKDF2-SHA256 admin password hash |
| `fanic backup-data` | Create a ZIP backup of the database and media |
| `fanic restore-data <zip>` | Restore from a backup archive |

## Architecture Overview

FANIC uses **file-based routing** via Cylinder. Each route handler lives in a file whose path mirrors the URL:

```
src/fanic/cylinder_sites/fanicsite/
├── ex.get.py                          → GET  /
├── works.ex.get.py                    → GET  /works/{work_id}
├── works.ex.post.py                   → POST /works/{work_id}
├── fanart.ex.get.py                   → GET  /fanart
├── fanart.ex.post.py                  → POST /fanart
├── ingest.ex.get.py                   → GET  /ingest
├── ingest.ex.post.py                  → POST /ingest
├── dmca.ex.get.py                     → GET  /dmca
├── dmca.ex.post.py                    → POST /dmca
├── feedback.ex.get.py                 → GET  /feedback
├── feedback.ex.post.py                → POST /feedback
├── faq.ex.get.py                      → GET  /faq
├── terms.ex.get.py                    → GET  /terms
├── cbz-format.ex.get.py              → GET  /cbz-format
├── update.ex.get.py                   → GET  /update
├── account/
│   ├── login.ex.get.py                → GET  /account/login
│   ├── login.ex.post.py               → POST /account/login
│   └── logout.ex.post.py              → POST /account/logout
├── user/
│   ├── profile.ex.get.py              → GET  /user/profile
│   ├── profile.ex.post.py             → POST /user/profile
│   ├── notifications.ex.get.py        → GET  /user/notifications
│   └── notifications.ex.post.py       → POST /user/notifications
├── users.ex.get.py                    → GET  /users/{username}
├── admin/
│   ├── users.ex.get.py                → GET  /admin/users
│   ├── users.ex.post.py               → POST /admin/users
│   ├── reports.ex.get.py              → GET  /admin/reports
│   └── reports.ex.post.py             → POST /admin/reports
├── tools/
│   └── reader.ex.get.py              → GET  /tools/reader/{work_id}
└── api/
    └── (see API Surface below)
```

Key modules:

| Module | Role |
|--------|------|
| `cylinder_main.py` | WSGI app factory, middleware (CSRF, session, alpha gate) |
| `db.py` | SQLite schema, migrations, query helpers |
| `repository.py` | Data-access layer (works, tags, users, bookmarks, notifications) |
| `ingest.py` | CBZ extraction, AVIF conversion, metadata parsing |
| `moderation.py` | Two-gate content filter (style + NSFW) |
| `clip_backend.py` | OpenCLIP model loading and inference |
| `style_classifier.py` | Image style classification (illustrated, anime, photorealistic, …) |
| `nsfw_detector.py` | NSFW scoring via CLIP text-image similarity |
| `fanart.py` | Fanart upload, content-addressed storage, auto-rating |
| `settings.py` | Pydantic-based configuration from environment variables |

## Content Moderation

Every uploaded image passes through a two-gate AI pipeline before it is accepted:

1. **Style gate** — An OpenCLIP ViT-L-14 model classifies the image style (`illustrated`, `anime`, `painterly`, `cgi`, or `photorealistic`). Photorealistic images are rejected outright because FANIC is an illustrated-content archive.
2. **NSFW gate** — CLIP text-image similarity scores the image as `sfw` or `explicit`. Images above the configurable threshold (`FANIC_EXPLICIT_THRESHOLD`, default 0.7) are blocked.

Moderation runs during both CBZ ingest and fanart upload.

## Fanart Gallery

Users can upload standalone illustrations alongside the comic archive. Fanart is stored content-addressed (SHA-256 digest), auto-converted to AVIF, and run through the same moderation pipeline. The gallery is browsable at `/fanart`.

## User System

- **Profiles** — display name, reading history, uploaded works, fanart, and bookmarks at `/users/{username}`.
- **Bookmarks** — save a page position with an optional note.
- **Notifications** — kudos, comments, and bookmark activity feed at `/user/notifications`.
- **Theme preferences** — per-user TOML-based theme configuration.

## Admin Dashboard

Accessible at `/admin/*` for users with an admin role:

- **User management** (`/admin/users`) — create, update, deactivate users and assign roles (superadmin / admin / user / guest).
- **Reports** (`/admin/reports`) — review and resolve DMCA takedown requests and general feedback.

## Alpha Invite Gate

When `FANIC_ALPHA_INVITE_GATE_ENABLED=true`, visitors must enter a valid invite code before accessing any part of the site. Valid codes are set via `FANIC_ALPHA_INVITE_CODES_CSV` (comma-separated). Accepted users receive a signed cookie lasting `FANIC_ALPHA_INVITE_COOKIE_MAX_AGE` seconds (default 30 days).

## API Surface

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/auth` | Check login status (`{logged_in, username}`) |
| `POST` | `/api/auth/login` | Authenticate with username + password |
| `POST` | `/api/auth/logout` | Clear session |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Service + database health check |

### Works

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/works` | List works (filters: `q`, `fandom`, `tag`, `rating`, `status`) |
| `GET` | `/api/works/{work_id}` | Work detail |
| `GET` | `/api/works/{work_id}/manifest` | Page manifest for the reader |
| `GET` | `/api/works/{work_id}/versions` | List work versions |
| `GET` | `/api/works/{work_id}/versions/{version_id}` | Version detail |
| `GET` | `/api/works/{work_id}/download` | Download original CBZ |
| `GET` | `/api/works/{work_id}/pages/{page_index}/image` | Full-size page image |
| `GET` | `/api/works/{work_id}/pages/{page_index}/thumb` | Page thumbnail |
| `GET` | `/api/works/{work_id}/progress?user_id=` | Reading progress |
| `POST` | `/api/works/{work_id}/progress` | Save reading progress |
| `POST` | `/api/works/{work_id}/bookmark` | Create/update bookmark |

### Ingest

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/ingest` | Upload CBZ + metadata (returns moderation result) |
| `POST` | `/api/ingest/metadata` | Extract metadata from CBZ without full ingest |
| `GET` | `/api/ingest/progress?token=` | Poll ingest progress |

## Windows Nginx Setup (Scripted)

Use the included script to install nginx on Windows, serve `/static/*`, `/works/*`, and `/fanart/*` from local files, and proxy all other routes to the WSGI app.

```powershell
just setup-nginx-windows
```

The script prompts for nginx version, install directory, listen port, upstream WSGI host/port, and repository root. It then downloads nginx, writes `nginx.conf`, configures static/media aliases, proxies everything else to Waitress, and validates + starts nginx.

To relocate storage and automatically update both WSGI (`FANIC_DATA_DIR`) and nginx aliases:

```powershell
just relocate-storage "C:/path/to/new/storage"
```

## Configuration

FANIC is configured via environment variables (or a `.env` file). Key groups:

### Core

| Variable | Default | Purpose |
|----------|---------|---------|
| `FANIC_ENVIRONMENT` | `development` | `development` or `production` |
| `FANIC_DATA_DIR` | `./data/` | Storage root for database, CBZ, works, and fanart |
| `FANIC_REQUIRE_HTTPS` | `true` | Enforce HTTPS for form POSTs |
| `FANIC_CSRF_PROTECT` | `true` | CSRF token validation |
| `FANIC_SESSION_SECRET` | *(dev default)* | JWT session signing key — **change in production** |
| `FANIC_SESSION_MAX_AGE` | `43200` | Session lifetime (seconds) |
| `FANIC_SESSION_SECURE` | `false` | Secure cookie flag (auto-enabled in production) |
| `FANIC_SESSION_COOKIE_SAMESITE` | `Lax` | SameSite cookie policy |
| `FANIC_MEDIA_BASE_URL` | `http://127.0.0.1:8080` | Base URL for media assets (CDN/nginx) |
| `FANIC_LOG_PATH_TEMPLATE` | `logs/%TIMESTAMP%` | Log file path (`%TIMESTAMP%` placeholder supported) |

### Auth & Rate Limiting

| Variable | Default | Purpose |
|----------|---------|---------|
| `FANIC_ADMIN_USERNAME` | `admin` | Admin account username |
| `FANIC_ADMIN_PASSWORD_HASH` | *(sha256 of "admin")* | Hash in `sha256$…` or `pbkdf2_sha256$…` format |
| `FANIC_AUTH_MAX_FAILURES` | `5` | Failed attempts before lockout |
| `FANIC_AUTH_WINDOW_SECONDS` | `300` | Lockout attempt window |
| `FANIC_AUTH_LOCKOUT_SECONDS` | `900` | Lockout duration |
| `FANIC_UPLOAD_RATE_WINDOW_SECONDS` | `60` | Upload rate-limit window |
| `FANIC_UPLOAD_RATE_MAX_REQUESTS` | `20` | Max uploads per window |
| `FANIC_UPLOAD_MAX_CONCURRENT_PER_USER` | `2` | Concurrent upload limit per user |

### Upload Limits

| Variable | Default | Purpose |
|----------|---------|---------|
| `FANIC_MAX_CBZ_UPLOAD_BYTES` | 256 MiB | Max CBZ file size |
| `FANIC_MAX_PAGE_UPLOAD_BYTES` | 20 MiB | Max single page image size |
| `FANIC_MAX_UPLOAD_IMAGE_PIXELS` | 40 M | Max image resolution |
| `FANIC_MAX_INGEST_PAGES` | `2000` | Max pages per ingest |
| `FANIC_MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES` | 128 MiB | Max uncompressed size per CBZ member |
| `FANIC_MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES` | 2 GiB | Max total uncompressed CBZ size |
| `FANIC_USER_PAGE_SOFT_CAP` | `2000` | After this many pages, AVIF quality ramps down |
| `FANIC_USER_PAGE_QUALITY_RAMP_MULTIPLIER` | `1.5` | Quality reaches 1 at cap × multiplier |

### AI / Moderation

| Variable | Default | Purpose |
|----------|---------|---------|
| `FANIC_EXPLICIT_THRESHOLD` | `0.7` | NSFW score threshold (0–1) |
| `FANIC_STYLE_MIN_CONFIDENCE` | `0.6` | Style classifier confidence floor |
| `FANIC_STYLE_MIN_CONFIDENCE_PHOTOREALISTIC` | `0.90` | Higher bar for photorealistic blocking |
| `FANIC_OPENCLIP_CACHE_DIR` | `~/.cache/clip/` | Model cache directory |
| `FANIC_PRELOAD_MODELS` | `true` | Preload CLIP models on startup |

### Image Quality

| Variable | Default | Purpose |
|----------|---------|---------|
| `FANIC_THUMBNAIL_AVIF_QUALITY` | `30` | Thumbnail AVIF quality (1–100) |
| `FANIC_IMAGE_AVIF_QUALITY` | `60` | Full-size page AVIF quality (1–100) |

In development mode (`FANIC_ENVIRONMENT=development`), HTTPS and CSRF enforcement are disabled for local workflow compatibility.

Generate a ready-to-paste admin password hash:

```powershell
uv run fanic hash-admin-password
# or non-interactive:
uv run fanic hash-admin-password --password "change-me-now"
```

## Metadata

You can provide metadata either:

- via `ComicInfo.xml` inside the CBZ, or
- as a separate JSON file passed to `--metadata`.

Example metadata:

```json
{
	"title": "Example Comic",
	"slug": "example-comic",
	"summary": "A fan comic about...",
	"creators": ["Artist Name", "Writer Name"],
	"fandoms": ["Zootopia"],
	"relationships": ["Nick Wilde/Judy Hopps"],
	"characters": ["Nick Wilde", "Judy Hopps"],
	"freeform_tags": ["Detective AU", "Slow Burn"],
	"rating": "Teen",
	"warnings": ["No Archive Warnings Apply"],
	"language": "en",
	"series": "Metro Cases",
	"series_index": 2,
	"status": "complete",
	"published_at": "2026-03-20",
	"cover_page_index": 1,
	"page_order": ["001.jpg", "002.jpg", "003.jpg"]
}
```

## Storage Layout

By default, data is stored under `src/fanic/storage` unless `FANIC_DATA_DIR` is set.

```text
storage/
	fanic.db
	cbz/
		<work_id>.cbz
	works/
		<work_id>/
			pages/        # full-size AVIF pages
			thumbs/       # AVIF thumbnails
	fanart/
		_objects/
			<digest[:2]>/<digest>.avif   # content-addressed fanart
	static/               # CSS, JS, images
```

## Backup And Restore

FANIC provides CLI commands to back up and restore runtime data (`fanic.db`, `cbz/`, `works/`, and `fanart/`).

Create a backup:

```powershell
# default output location: .\backups\fanic-backup-YYYYMMDD-HHMMSS.zip
uv run fanic backup-data

# explicit backup path
uv run fanic backup-data --output C:\backups\fanic-20260322.zip

# replace an existing archive
uv run fanic backup-data --output C:\backups\fanic-latest.zip --overwrite
```

Restore from a backup:

```powershell
# restore into an empty data directory
uv run fanic restore-data C:\backups\fanic-20260322.zip

# overwrite existing data directory contents
uv run fanic restore-data C:\backups\fanic-20260322.zip --force

# create a pre-restore safety snapshot, then restore
uv run fanic restore-data C:\backups\fanic-20260322.zip --force --snapshot-before-restore

# control where the pre-restore safety snapshot is written
uv run fanic restore-data C:\backups\fanic-20260322.zip --force --snapshot-before-restore --snapshot-output C:\backups\fanic-pre-restore.zip
```

Suggested production procedure:

1. Stop the app process.
2. Run `uv run fanic backup-data --output <path-to-backup.zip>`.
3. Copy the backup archive to durable storage (off-host if possible).
4. For restore, stop the app process first, then run `uv run fanic restore-data <path-to-backup.zip> --force --snapshot-before-restore`.
5. Start the app and validate a sample work, page image, and metadata record.

## Database

FANIC uses SQLite. The schema lives in `src/fanic/sql/schema.sql` and covers:

- **works** — comic metadata (title, slug, summary, rating, series, page count, etc.)
- **pages** — per-work page images and thumbnails with dimensions
- **tags / tag_synonyms / work_tags** — structured tagging with canonicalization
- **fanart_items** — uploaded illustrations with moderation metadata
- **users** — accounts with roles (superadmin, admin, user, guest)
- **reading_progress** — per-user page position per work
- **user_bookmarks** — saved pages with optional notes
- **notifications** — activity feed (kudos, comments, bookmarks)
- **content_reports** — DMCA takedown requests
- **user_feedback** — bug reports and general feedback

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python ≥ 3.13 |
| Web framework | [Cylinder](https://github.com/rbroderi/cylinder) (file-based WSGI routing) |
| WSGI server | Waitress |
| Database | SQLite |
| Auth | Authlib (JWT sessions) |
| Config | Pydantic + python-dotenv |
| Image processing | Pillow + pillow-avif-plugin |
| AI / moderation | OpenCLIP (open-clip-torch) + PyTorch |
| Lazy loading | lazi (deferred ML model imports) |
| Runtime types | beartype |
| Logging | structlog |
| Linting | Ruff |
| Dev tools | autopep695, pytest, pytest-cov |

## ComicInfo Schema Validation

This repository includes the ComicInfo v2.0 XSD at `schema/comicinfo/v2.0/ComicInfo.xsd` and validates matching XML files in both local hooks and CI.

Validate one file manually:

```powershell
uvx --with xmlschema python scripts/validate_comicinfo_xsd.py examples/ComicInfo.xml
```

Run the pre-commit hook manually:

```powershell
uvx prek run comicinfo-xsd --all-files
```

The GitHub Actions workflow `ComicInfo XSD` also runs this check on push and pull requests when ComicInfo files or schema-validation tooling changes.

## Contributing

See [AGENTS.md](AGENTS.md) for project-specific coding conventions (ternary coalescing style, import re-export aliases, file-based routing rules, `StrEnum` for finite choices, `match`/`case` dispatch, and more).

Tests live in `tests/` and cover routes, moderation, ingest, and utilities:

```powershell
uv run pytest
uv run pytest --cov
```

Example files live in `examples/`, including `examples/ComicInfo.xml` and `examples/theme_example.toml`.
