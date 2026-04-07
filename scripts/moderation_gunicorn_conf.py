import faulthandler
import os
import signal
import sys
import threading
import time
import traceback
from typing import Any


def _dump_worker_diagnostics(reason: str) -> None:
    pid = os.getpid()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sys.stderr.write(
        f"\n[fanic-moderation] worker diagnostics start pid={pid} reason={reason} ts={timestamp}\n"
    )
    # Dump all thread traces from the current worker process.
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    current_frames = sys._current_frames()  # pyright: ignore[reportPrivateUsage]
    for thread in threading.enumerate():
        ident = thread.ident
        if ident is None:
            continue
        frame = current_frames.get(ident)
        if frame is None:
            continue
        sys.stderr.write(
            f"\n[fanic-moderation] thread={thread.name} ident={ident} daemon={thread.daemon}\n"
        )
        traceback.print_stack(frame, file=sys.stderr)
    sys.stderr.write("[fanic-moderation] worker diagnostics end\n")
    sys.stderr.flush()


def worker_abort(worker: Any) -> None:  # type: ignore[no-untyped-def]
    _ = worker
    _dump_worker_diagnostics("worker_abort")


def worker_int(worker: Any) -> None:  # type: ignore[no-untyped-def]
    _ = worker
    _dump_worker_diagnostics("worker_int")


# Ensure faulthandler handles these signals in addition to gunicorn hooks.
faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)
