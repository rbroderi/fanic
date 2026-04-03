from pathlib import Path
from typing import Any
from typing import final

import pytest

import fanic.cylinder_sites.common.security as security
from fanic.cylinder_sites.common.protocols import CookieMapLike
from fanic.cylinder_sites.common.protocols import FileMapLike
from fanic.cylinder_sites.common.protocols import FormLike
from fanic.cylinder_sites.common.protocols import QueryArgsLike


@final
class _Upload:
    def __init__(self, filename: str | None, content_type: str) -> None:
        self.filename: str | None = filename
        self.content_type: str = content_type

    def save(self, dst: str | Path) -> None:
        Path(dst).write_bytes(b"")


@final
class _StringMap:
    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data: dict[str, str] = data if data is not None else {}

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)


@final
class _FileMap:
    def __init__(self, data: dict[str, _Upload] | None = None) -> None:
        self._data: dict[str, _Upload] = data if data is not None else {}

    def get(self, key: str) -> _Upload | None:
        return self._data.get(key)


@final
class _Request:
    path: str
    method: str
    scheme: str
    headers: dict[str, str]
    environ: dict[str, object]
    args: QueryArgsLike
    form: FormLike
    files: FileMapLike
    cookies: CookieMapLike
    remote_addr: str

    def __init__(
        self,
        *,
        path: str = "/",
        method: str = "GET",
        scheme: str = "http",
        headers: dict[str, str] | None = None,
        environ: dict[str, object] | None = None,
        args: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        files: dict[str, _Upload] | None = None,
        cookies: dict[str, str] | None = None,
        remote_addr: str = "",
    ) -> None:
        self.path = path
        self.method = method
        self.scheme = scheme
        self.headers = headers if headers is not None else {}
        self.environ = environ if environ is not None else {}
        self.args = _StringMap(args)
        self.form = _StringMap(form)
        self.files = _FileMap(files)
        self.cookies = _StringMap(cookies)
        self.remote_addr = remote_addr


@final
class _Response:
    status_code: int
    content_type: str
    headers: dict[str, str]
    data: bytes

    def __init__(self) -> None:
        self.status_code = 200
        self.content_type = "text/plain"
        self.headers = {}
        self.data = b""

    def set_data(self, data: str | bytes) -> None:
        self.data = data.encode("utf-8") if isinstance(data, str) else data

    def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "Lax",
    ) -> None:
        del max_age, path, secure, httponly, samesite
        self.headers["Set-Cookie"] = f"{key}={value}"

    def delete_cookie(self, key: str, path: str = "/") -> None:
        del path
        self.headers["Set-Cookie"] = f"{key}=; Max-Age=0"


def test_upload_policy_validation_paths() -> None:
    bad_ext = security.validate_cbz_upload_policy(_Upload("pages.zip", "application/x-cbz"))
    assert bad_ext is not None

    bad_type = security.validate_cbz_upload_policy(_Upload("pages.cbz", "text/plain"))
    assert bad_type is not None

    good_cbz = security.validate_cbz_upload_policy(_Upload("pages.cbz", "application/x-cbz"))
    assert good_cbz is None

    good_page_no_type = security.validate_page_upload_policy(_Upload("page.png", ""))
    assert good_page_no_type is None

    bad_page = security.validate_page_upload_policy(_Upload("page.txt", "image/png"))
    assert bad_page is not None


def test_upload_size_and_policy_error_mapping(tmp_path: Path) -> None:
    file_path = tmp_path / "upload.bin"
    file_path.write_bytes(b"123456")

    message = security.validate_saved_upload_size(file_path, 4, "CBZ upload")
    assert message is not None
    info = security.upload_policy_error_info(message)
    assert info.error_code == "upload_too_large"
    assert info.status_code == 413

    assert security.upload_policy_error_info("Unsupported content type").status_code == 415
    assert security.upload_policy_error_info("random").status_code == 400


def test_request_is_secure_paths() -> None:
    assert security.request_is_secure(_Request(scheme="https")) is True
    assert security.request_is_secure(_Request(headers={"X-Forwarded-Proto": "https"})) is True
    assert security.request_is_secure(_Request(headers={"Forwarded": "for=1.1.1.1;proto=https"})) is True
    assert security.request_is_secure(_Request(environ={"wsgi.url_scheme": "https"})) is True
    assert security.request_is_secure(_Request(environ={"HTTP_X_FORWARDED_SSL": "on"})) is True
    assert security.request_is_secure(_Request()) is False


def test_enforce_https_termination_redirects_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security, "REQUIRE_HTTPS", True)

    request = _Request(path="/comic/abc", headers={"Host": "fanic.media"})
    response = _Response()

    allowed = security.enforce_https_termination(request, response)

    assert allowed is False
    assert response.status_code == 301
    assert response.headers["Location"] == "https://fanic.media/comic/abc"


def test_enforce_https_termination_allows_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security, "REQUIRE_HTTPS", False)
    assert security.enforce_https_termination(_Request(), _Response()) is True


def test_validate_csrf_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    @final
    class _Logger:
        def warning(self, *args: object, **kwargs: object) -> None:
            events.append((tuple(args), dict(kwargs)))

    monkeypatch.setattr(security, "LOGGER", _Logger())

    monkeypatch.setattr(security, "CSRF_PROTECT", False)
    assert security.validate_csrf(_Request()) is True

    monkeypatch.setattr(security, "CSRF_PROTECT", True)
    missing = _Request(path="/upload", form={}, cookies={}, remote_addr="1.2.3.4")
    assert security.validate_csrf(missing) is False

    mismatch = _Request(
        path="/upload",
        form={"csrf_token": "abc"},
        cookies={security.CSRF_COOKIE_NAME: "def"},
        remote_addr="1.2.3.4",
    )
    assert security.validate_csrf(mismatch) is False

    match = _Request(
        form={"csrf_token": "same"},
        cookies={security.CSRF_COOKIE_NAME: "same"},
    )
    assert security.validate_csrf(match) is True
    assert len(events) >= 2


def test_request_client_ip_prefers_forwarded_header() -> None:
    request = _Request(headers={"X-Forwarded-For": "9.9.9.9, 8.8.8.8"}, remote_addr="1.1.1.1")
    assert security._request_client_ip(request) == "9.9.9.9"  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
