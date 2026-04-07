#!/usr/bin/env python3
import argparse
import json
import socket
import statistics
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import override
from zipfile import ZipFile

IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".avif",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
}


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__(host="localhost", timeout=timeout)
        self._socket_path: str = socket_path

    @override
    def connect(self) -> None:
        unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        unix_socket.settimeout(
            float(self.timeout) if self.timeout is not None else None
        )
        unix_socket.connect(self._socket_path)
        self.sock: socket.SocketType = unix_socket


def _resolve_member_payload(
    cbz_path: Path, member_name: str | None
) -> tuple[str, bytes, str]:
    with ZipFile(cbz_path, "r") as cbz_file:
        members = sorted(
            name
            for name in cbz_file.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in IMAGE_SUFFIXES
        )
        if not members:
            raise RuntimeError(f"No image members found in {cbz_path}")

        selected = member_name if member_name and member_name in members else members[0]
        payload = cbz_file.read(selected)
        suffix = Path(selected).suffix if Path(selected).suffix else ".png"
        return selected, payload, suffix


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    index = int((len(ordered) - 1) * 0.95)
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stress test moderation sidecar latency"
    )
    parser.add_argument(
        "--cbz", default="tests/media/mod_test.cbz", help="CBZ path to read a page from"
    )
    parser.add_argument("--member", default="", help="Specific CBZ member name to test")
    parser.add_argument(
        "--socket", default="/run/fanic/fanic-moderation.sock", help="Unix socket path"
    )
    parser.add_argument(
        "--iterations", type=int, default=20, help="Number of moderation requests"
    )
    parser.add_argument(
        "--timeout", type=float, default=180.0, help="Per-request timeout seconds"
    )
    parser.add_argument("--token", default="", help="Optional sidecar auth token")
    args = parser.parse_args()

    cbz_path = Path(args.cbz)
    if not cbz_path.exists():
        raise RuntimeError(f"CBZ not found: {cbz_path}")

    member_name = args.member.strip() if args.member else None
    member, payload, suffix = _resolve_member_payload(cbz_path, member_name)

    elapsed_ms_values: list[float] = []
    failures: list[str] = []

    print(
        json.dumps(
            {
                "cbz": str(cbz_path),
                "member": member,
                "bytes": len(payload),
                "suffix": suffix,
            },
            ensure_ascii=True,
        )
    )

    for index in range(1, args.iterations + 1):
        started_at = time.perf_counter()
        connection = UnixHTTPConnection(args.socket, timeout=args.timeout)
        try:
            headers = {
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
                "X-Fanic-File-Suffix": suffix,
            }
            if args.token:
                headers["X-Fanic-Moderation-Token"] = args.token
            connection.request(
                "POST", "/moderate-image-bytes", body=payload, headers=headers
            )
            response = connection.getresponse()
            response_body = response.read()
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            elapsed_ms_values.append(elapsed_ms)
            ok = response.status < 400
            print(
                f"iter {index:03d}/{args.iterations} status={response.status} elapsed_ms={elapsed_ms:.1f} ok={ok}"
            )
            if not ok:
                failures.append(
                    f"status={response.status} body={response_body[:300]!r}"
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            elapsed_ms_values.append(elapsed_ms)
            failures.append(f"exception={exc}")
            print(
                f"iter {index:03d}/{args.iterations} status=EXC elapsed_ms={elapsed_ms:.1f} ok=False error={exc}"
            )
        finally:
            connection.close()

    avg_ms = statistics.mean(elapsed_ms_values)
    med_ms = statistics.median(elapsed_ms_values)
    p95_ms = _p95(elapsed_ms_values)
    max_ms = max(elapsed_ms_values)
    min_ms = min(elapsed_ms_values)
    summary = {
        "iterations": args.iterations,
        "failures": len(failures),
        "avg_ms": round(avg_ms, 1),
        "median_ms": round(med_ms, 1),
        "p95_ms": round(p95_ms, 1),
        "min_ms": round(min_ms, 1),
        "max_ms": round(max_ms, 1),
    }
    print(json.dumps(summary, ensure_ascii=True))
    if failures:
        print("failure_samples:")
        for item in failures[:5]:
            print(item)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
