from __future__ import annotations

import argparse
import atexit
import functools
import logging
import signal
from collections.abc import Callable
from pathlib import Path
from types import FrameType

from fanic.cylinder_main import serve as serve
from fanic.db import initialize_database
from fanic.ingest import convert_existing_thumbs_to_avif
from fanic.ingest import ingest_cbz
from fanic.settings import get_settings

OK = 0
ERROR = 1


def once_only(func: Callable[..., int]) -> Callable[..., int]:
    called = False
    result = OK

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> int:
        nonlocal called
        nonlocal result

        if called:
            return result

        result = func(*args, **kwargs)
        called = True
        return result

    return wrapper


def _enable_beartype() -> None:
    if not get_settings().enable_beartype:
        return
    from beartype.claw import beartype_package

    logging.getLogger(__name__).error(
        "Enabling beartype runtime type checking for fanic"
    )
    beartype_package("fanic")


_enable_beartype()


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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    match args.command:
        case "init-db":
            result_code = initialize_database(reset=True)
            print("Database and storage reset, then schema initialized")
            return result_code
        case "ingest":
            initialize_database()
            result = ingest_cbz(args.cbz, args.metadata)
            print(f"Ingested {result['work_id']} ({result['page_count']} pages)")
            return OK
        case "convert-thumbs-avif":
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
            return OK
        case "serve":
            return serve(host=args.host, port=args.port)
        case _:
            return ERROR


def cleanup_on_shutdown() -> int:
    """Placeholder for graceful shutdown cleanup work.

    Add explicit cleanup here if/when the app introduces long-lived resources,
    such as:
    - persistent database pools or handles,
    - background workers/threads,
    - buffered telemetry/log exporters,
    - open file/network clients requiring an explicit close.
    """
    return OK


@once_only
def run_cleanup_once() -> int:
    return cleanup_on_shutdown()


def _handle_shutdown_signal(signum: int, frame: FrameType | None) -> None:
    _ = (signum, frame)
    print("Shutting down gracefully...", flush=True)
    raise SystemExit(OK)


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)


if __name__ == "__main__":
    atexit.register(run_cleanup_once)
    install_signal_handlers()
    main_error = OK
    try:
        main_error = main()
    except KeyboardInterrupt:
        print("Shutting down gracefully...", flush=True)
        main_error = OK
    finally:
        clean_error = run_cleanup_once()
    raise SystemExit(max(main_error, clean_error))
