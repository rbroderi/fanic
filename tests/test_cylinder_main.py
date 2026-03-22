from __future__ import annotations

import logging
from collections.abc import Callable
from wsgiref.types import WSGIApplication

import pytest

import fanic.cylinder_main as cylinder_main


def test_startup_invokes_dependencies_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_ensure_storage_dirs() -> None:
        calls.append("storage")

    def fake_initialize_database() -> int:
        calls.append("db")
        return 0

    def fake_initialize_moderation_models() -> dict[str, bool]:
        calls.append("moderation")
        return {"requested": False, "nsfw_ready": False, "style_ready": False}

    monkeypatch.setattr(cylinder_main, "ensure_storage_dirs", fake_ensure_storage_dirs)
    monkeypatch.setattr(cylinder_main, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(
        cylinder_main,
        "initialize_moderation_models",
        fake_initialize_moderation_models,
    )

    cylinder_main.startup()

    assert calls == ["storage", "db", "moderation"]


def test_create_app_calls_startup_and_cylinder_get_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    captured_log_level: list[int] = []
    captured_has_file_handler: list[bool] = []

    def fake_startup() -> None:
        calls.append("startup")

    def fake_get_app(
        app_map_fn: Callable[[], tuple[str, str, dict[str, object]]],
        log_level: int,
        log_handler: logging.Handler,
    ) -> WSGIApplication:
        site_path, site_name, config = app_map_fn()
        assert site_name == "fanicsite"
        assert isinstance(config, dict)
        assert site_path.endswith("cylinder_sites")
        captured_log_level.append(log_level)
        captured_has_file_handler.append(isinstance(log_handler, logging.FileHandler))
        calls.append("get_app")

        def fake_wsgi_app(
            environ: dict[str, object],
            start_response: Callable[..., object],
        ) -> list[bytes]:
            _ = (environ, start_response)
            return [b""]

        return fake_wsgi_app

    monkeypatch.setattr(cylinder_main, "startup", fake_startup)
    monkeypatch.setattr("fanic.cylinder_main.cylinder.get_app", fake_get_app)

    app = cylinder_main.create_app()

    assert callable(app)
    assert calls == ["startup", "get_app"]
    assert captured_log_level == [logging.DEBUG]
    assert captured_has_file_handler == [True]


def test_serve_invokes_waitress(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_app() -> str:
        return "app-object"

    def fake_waitress_serve(app: object, host: str, port: int) -> None:
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(cylinder_main, "create_app", fake_create_app)
    monkeypatch.setattr("fanic.cylinder_main.waitress.serve", fake_waitress_serve)

    result = cylinder_main.serve("127.0.0.1", 8000)

    assert result == 0
    assert captured == {"app": "app-object", "host": "127.0.0.1", "port": 8000}


def test_serve_handles_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_create_app() -> str:
        return "app-object"

    def fake_waitress_serve(app: object, host: str, port: int) -> None:
        _ = (app, host, port)
        raise KeyboardInterrupt()

    monkeypatch.setattr(cylinder_main, "create_app", fake_create_app)
    monkeypatch.setattr("fanic.cylinder_main.waitress.serve", fake_waitress_serve)

    result = cylinder_main.serve("127.0.0.1", 8000)

    captured = capsys.readouterr()
    assert result == 0
    assert "Shutting down gracefully..." in captured.out
