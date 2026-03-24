# FANIC: Fan Archive Nexus for Illustrated Comics

This project is a starter implementation of FANIC (Fan Archive Nexus for Illustrated Comics):

- CBZ is the source artifact.
- Pages are extracted server-side for fast browser delivery.
- Works are browsable with structured and freeform tags.
- A browser reader includes keyboard page flip, sidebar thumbnails, and saved page position.

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

Optional one-off: convert existing thumbnails to AVIF (q60).

```powershell
uv run fanic convert-thumbs-avif --dry-run
uv run fanic convert-thumbs-avif
```

4. Run the site.

```powershell
uv run fanic serve --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

## Windows Nginx Setup (Scripted)

Use the included script to install nginx on Windows, serve `/static/*`, `/works/*`, and `/fanart/*` from local files, and proxy all other routes to the WSGI app.

Run:

```powershell
just setup-nginx-windows
```

The script will prompt for:

- nginx version
- install directory
- listen port
- upstream WSGI host/port
- repository root

It then:

1. downloads and installs nginx,
2. writes `nginx.conf`,
3. serves static files from `src/fanic/storage/static` on `/static/`,
4. serves work media from `src/fanic/storage/works` on `/works/`,
5. serves fanart media from `src/fanic/storage/fanart` on `/fanart/`,
6. proxies everything else to your WSGI server (default `127.0.0.1:8000`),
5. validates config and starts or reloads nginx.

## Production Security Settings

Set these environment variables in production:

- `FANIC_ENV=production`
- `FANIC_REQUIRE_HTTPS=true` (enforces HTTPS termination for browser/auth POST flows)
- `FANIC_CSRF_PROTECT=true` (enables CSRF token validation on browser form POST endpoints)
- `FANIC_SESSION_SECURE=true` (optional override; production already enables secure cookies by default)
- `FANIC_SESSION_COOKIE_SAMESITE=Lax` (or `Strict` based on deployment needs)
- `FANIC_ADMIN_USERNAME=<admin-user>`
- `FANIC_ADMIN_PASSWORD_HASH=<hash>` where hash format is either:
	- `sha256$<hex-digest>`, or
	- `pbkdf2_sha256$<iterations>$<salt>$<hex-digest>`
- `FANIC_AUTH_MAX_FAILURES=5`
- `FANIC_AUTH_WINDOW_SECONDS=300`
- `FANIC_AUTH_LOCKOUT_SECONDS=900`
- `FANIC_UPLOAD_RATE_WINDOW_SECONDS=60`
- `FANIC_UPLOAD_RATE_MAX_REQUESTS=20`
- `FANIC_UPLOAD_MAX_CONCURRENT_PER_USER=2`
- `FANIC_MAX_CBZ_UPLOAD_BYTES=268435456`
- `FANIC_MAX_PAGE_UPLOAD_BYTES=20971520`
- `FANIC_MAX_INGEST_PAGES=2000`
- `FANIC_MAX_CBZ_MEMBER_UNCOMPRESSED_BYTES=134217728`
- `FANIC_MAX_CBZ_TOTAL_UNCOMPRESSED_BYTES=2147483648`
- `FANIC_MAX_UPLOAD_IMAGE_PIXELS=40000000`
- `FANIC_USER_PAGE_SOFT_CAP=2000`
- `FANIC_USER_PAGE_QUALITY_RAMP_MULTIPLIER=1.5`
- `FANIC_ALLOWED_CBZ_EXTENSIONS=.cbz`
- `FANIC_ALLOWED_CBZ_CONTENT_TYPES=application/zip,application/x-cbz,application/octet-stream`
- `FANIC_ALLOWED_PAGE_EXTENSIONS=.avif,.bmp,.gif,.jpeg,.jpg,.png,.tif,.tiff,.webp`
- `FANIC_ALLOWED_PAGE_CONTENT_TYPES=image/avif,image/bmp,image/gif,image/jpeg,image/png,image/tiff,image/webp,application/octet-stream`
- `FANIC_LOG_PATH_TEMPLATE=logs/%TIMESTAMP%` (supports `%TIMESTAMP%` placeholder, for example `logs/%TIMESTAMP%.log`)

User soft-cap image quality behavior:

- Pages 1 to `FANIC_USER_PAGE_SOFT_CAP` use normal `FANIC_IMAGE_AVIF_QUALITY`.
- After the soft cap, page-image AVIF quality ramps down linearly.
- At `FANIC_USER_PAGE_SOFT_CAP * FANIC_USER_PAGE_QUALITY_RAMP_MULTIPLIER`, quality reaches 1.

In development mode (`FANIC_ENV=development`), HTTPS and CSRF enforcement remain disabled by default for local workflow compatibility.

Generate a ready-to-paste admin password hash:

```powershell
uv run fanic hash-admin-password
# or non-interactive:
uv run fanic hash-admin-password --password "change-me-now"
```

Then set `FANIC_ADMIN_PASSWORD_HASH` to the printed value.

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

By default, data is stored under `src/fanic/storage`:

```text
storage/
	fanic.db
	cbz/
		<work_id>.cbz
	works/
		<work_id>/
			metadata.toml
			pages/
			thumbs/
```

Set `FANIC_DATA_DIR` to override this location.

## Backup And Restore

FANIC provides CLI commands to back up and restore runtime data (`fanic.db`, `cbz/`, and `works/`).

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

## API Surface (MVP)

- `GET /api/works`
- `GET /api/works/{work_id}`
- `GET /api/works/{work_id}/manifest`
- `GET /api/works/{work_id}/download`
- `GET /api/works/{work_id}/pages/{page_index}/image`
- `GET /api/works/{work_id}/pages/{page_index}/thumb`
- `GET /api/works/{work_id}/progress?user_id=anon`
- `POST /api/works/{work_id}/progress?page_index=1&user_id=anon`

## Notes

- This is intentionally a compact MVP scaffold.
- Tag canonicalization and synonym admin tooling are represented in schema (`tags`, `tag_synonyms`) and can be expanded next.
