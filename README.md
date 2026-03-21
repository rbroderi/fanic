# CO3: Fan Comic Archive MVP

This project is a starter implementation of an AO3-style fan comic archive:

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
uv run co3 init-db
```

3. Ingest a CBZ.

```powershell
uv run co3 ingest C:\path\to\comic.cbz --metadata C:\path\to\metadata.json
```

4. Run the site.

```powershell
uv run co3 serve --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000.

## Metadata

You can provide metadata either:

- as `comic.json` or `metadata.json` inside the CBZ, or
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

By default, data is stored under `src/co3/storage`:

```text
storage/
	co3.db
	cbz/
		<work_id>.cbz
	works/
		<work_id>/
			manifest.json
			metadata.json
			pages/
			thumbs/
```

Set `CO3_DATA_DIR` to override this location.

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
