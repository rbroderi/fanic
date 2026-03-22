from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fanic.cylinder_main import serve as serve
from fanic.db import initialize_database
from fanic.ingest import convert_existing_thumbs_to_avif
from fanic.ingest import ingest_cbz


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FANIC comic archive toolkit")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init_db = subcommands.add_parser("init-db", help="Initialize SQLite schema")
    init_db.set_defaults(command="init-db")

    ingest = subcommands.add_parser("ingest", help="Ingest a CBZ archive")
    ingest.add_argument("cbz", type=Path, help="Path to the source CBZ file")
    ingest.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Optional JSON metadata file to merge with ComicInfo.xml metadata",
    )
    ingest.set_defaults(command="ingest")

    convert_thumbs = subcommands.add_parser(
        "convert-thumbs-avif",
        help="Convert existing page thumbnails to AVIF",
    )
    convert_thumbs.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview conversion results without writing files or database changes",
    )
    convert_thumbs.set_defaults(command="convert-thumbs-avif")

    runserver = subcommands.add_parser("serve", help="Run local web server")
    runserver.add_argument("--host", default="127.0.0.1")
    runserver.add_argument("--port", default=8000, type=int)
    runserver.set_defaults(command="serve")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        initialize_database(reset=True)
        print("Database and storage reset, then schema initialized")
        return

    if args.command == "ingest":
        initialize_database()
        result = ingest_cbz(args.cbz, args.metadata)
        print(f"Ingested {result['work_id']} ({result['page_count']} pages)")
        return

    if args.command == "convert-thumbs-avif":
        initialize_database()
        result = convert_existing_thumbs_to_avif(dry_run=bool(args.dry_run))
        print(
            "Thumb conversion "
            f"(dry_run={result['dry_run']}): "
            f"scanned={result['scanned']}, "
            f"converted={result['converted']}, "
            f"already_avif={result['already_avif']}, "
            f"missing_source={result['missing_source']}, "
            f"failed={result['failed']}, "
            f"updated_rows={result['updated_rows']}"
        )
        return

    if args.command == "serve":
        serve(host=args.host, port=args.port)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Shutting down gracefully...")
        sys.exit(0)
