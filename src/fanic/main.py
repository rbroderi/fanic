from __future__ import annotations

import argparse
import atexit
import functools
import getpass
import hashlib
import logging
import secrets
import signal
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fanic.db import initialize_database
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

    hash_password = subcommands.add_parser(
        "hash-admin-password",
        help="Generate a pbkdf2_sha256 hash for FANIC_ADMIN_PASSWORD_HASH",
    )
    hash_password.add_argument(
        "--password",
        default=None,
        help="Password to hash (omit to be prompted securely)",
    )
    hash_password.add_argument(
        "--rounds",
        default=390000,
        type=int,
        help="PBKDF2 iteration count",
    )
    hash_password.add_argument(
        "--salt-bytes",
        default=16,
        type=int,
        help="Random salt size in bytes",
    )
    hash_password.set_defaults(command="hash-admin-password")

    backup_data = subcommands.add_parser(
        "backup-data",
        help="Create a ZIP backup of fanic.db, cbz/, and works/",
    )
    backup_data.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .zip path (default: ./backups/fanic-backup-<timestamp>.zip)",
    )
    backup_data.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output archive if it already exists",
    )
    backup_data.set_defaults(command="backup-data")

    restore_data = subcommands.add_parser(
        "restore-data",
        help="Restore fanic.db, cbz/, and works/ from a ZIP backup",
    )
    restore_data.add_argument("backup", type=Path, help="Path to a .zip backup")
    restore_data.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing data directory contents",
    )
    restore_data.add_argument(
        "--snapshot-before-restore",
        action="store_true",
        help="Create a safety backup of current runtime data before restore",
    )
    restore_data.add_argument(
        "--snapshot-output",
        type=Path,
        default=None,
        help="Pre-restore backup .zip path (default: ./backups/fanic-pre-restore-<timestamp>.zip)",
    )
    restore_data.add_argument(
        "--snapshot-overwrite",
        action="store_true",
        help="Overwrite the pre-restore backup archive if it already exists",
    )
    restore_data.set_defaults(command="restore-data")

    return parser


def _pbkdf2_admin_password_hash(password: str, rounds: int, salt_bytes: int) -> str:
    salt = secrets.token_hex(salt_bytes)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        rounds,
    ).hex()
    return f"pbkdf2_sha256${rounds}${salt}${digest}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    match args.command:
        case "init-db":
            result_code = initialize_database(reset=True)
            print("Database and storage reset, then schema initialized")
            return result_code
        case "ingest":
            from fanic.ingest import ingest_cbz

            initialize_database()
            result = ingest_cbz(args.cbz, args.metadata)
            print(f"Ingested {result['work_id']} ({result['page_count']} pages)")
            return OK
        case "convert-thumbs-avif":
            from fanic.ingest import convert_existing_thumbs_to_avif

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
            from fanic.cylinder_main import serve as serve

            return serve(host=args.host, port=args.port)
        case "hash-admin-password":
            password = (
                str(args.password)
                if args.password is not None
                else getpass.getpass("Admin password: ")
            )
            if not password:
                print("Password must not be empty")
                return ERROR

            rounds = int(args.rounds)
            salt_bytes = int(args.salt_bytes)
            if rounds < 10000:
                print("rounds must be at least 10000")
                return ERROR
            if salt_bytes < 8:
                print("salt-bytes must be at least 8")
                return ERROR

            hashed = _pbkdf2_admin_password_hash(password, rounds, salt_bytes)
            print(f"FANIC_ADMIN_PASSWORD_HASH={hashed}")
            return OK
        case "backup-data":
            from fanic.db import create_runtime_backup as create_runtime_backup

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = (
                args.output
                if args.output is not None
                else Path.cwd() / "backups" / f"fanic-backup-{timestamp}.zip"
            )
            resolved_backup_path = backup_path.expanduser().resolve()
            if resolved_backup_path.exists() and bool(args.overwrite):
                resolved_backup_path.unlink()

            try:
                created_path = create_runtime_backup(resolved_backup_path)
            except (FileExistsError, ValueError) as exc:
                print(str(exc))
                return ERROR

            print(f"Backup created: {created_path}")
            return OK
        case "restore-data":
            from fanic.db import create_runtime_backup as create_runtime_backup
            from fanic.db import restore_runtime_backup as restore_runtime_backup

            if bool(args.snapshot_before_restore):
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                snapshot_path = (
                    args.snapshot_output
                    if args.snapshot_output is not None
                    else Path.cwd() / "backups" / f"fanic-pre-restore-{timestamp}.zip"
                )
                resolved_snapshot_path = snapshot_path.expanduser().resolve()
                if resolved_snapshot_path.exists() and bool(args.snapshot_overwrite):
                    resolved_snapshot_path.unlink()

                try:
                    created_snapshot_path = create_runtime_backup(
                        resolved_snapshot_path
                    )
                except (FileExistsError, ValueError) as exc:
                    print(f"Pre-restore backup failed: {exc}")
                    return ERROR

                print(f"Pre-restore backup created: {created_snapshot_path}")

            try:
                restore_runtime_backup(args.backup, force=bool(args.force))
            except (FileExistsError, FileNotFoundError, ValueError) as exc:
                print(str(exc))
                return ERROR

            print("Restore complete")
            return OK
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
    print("Shutting down gracefully...", flush=True)
    return OK


@once_only
def run_cleanup_once() -> int:
    return cleanup_on_shutdown()


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, run_cleanup_once)
    signal.signal(signal.SIGTERM, run_cleanup_once)


if __name__ == "__main__":
    atexit.register(run_cleanup_once)
    _install_signal_handlers()
    main_error = OK
    try:
        main_error = main()
    except KeyboardInterrupt:
        pass
    finally:
        clean_error = run_cleanup_once()
    raise SystemExit(max(main_error, clean_error))
