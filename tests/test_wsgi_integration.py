from __future__ import annotations

from collections.abc import Callable
from typing import Any
from wsgiref.types import StartResponse

from fanic.cylinder_main import create_app

type WriteCallable = Callable[[bytes], object]


def _call_app(path: str) -> tuple[int, bytes]:
    app = create_app()

    captured: dict[str, Any] = {"status": "500 Internal Server Error"}

    def start_response(
        status: str,
        headers: list[tuple[str, str]],
        exc_info: Any = None,
        /,
    ) -> WriteCallable:
        _ = (headers, exc_info)
        captured["status"] = status

        def _write(data: bytes) -> object:
            _ = data
            return object()

        return _write

    environ = {
        "REQUEST_METHOD": "GET",
        "SCRIPT_NAME": "",
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "CONTENT_TYPE": "",
        "CONTENT_LENGTH": "0",
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": None,
        "wsgi.errors": None,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }

    start_response_callback: StartResponse = start_response
    result = app(environ, start_response_callback)
    chunks: list[bytes] = []
    try:
        for chunk in result:
            chunks.append(chunk)
    finally:
        close = getattr(result, "close", None)
        if callable(close):
            close()

    status_code_text = str(captured["status"]).split(" ", 1)[0]
    status_code = int(status_code_text)
    return status_code, b"".join(chunks)


def test_wsgi_home_page_responds_ok() -> None:
    status_code, body = _call_app("/")
    assert status_code == 200
    assert b"FANIC" in body


def test_wsgi_missing_work_returns_404() -> None:
    status_code, body = _call_app("/works/does-not-exist")
    assert status_code == 404
    assert b"Work not found" in body or b"Not found" in body
