"""protocols common domain implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class QueryArgsLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class FormLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class CookieMapLike(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


@runtime_checkable
class FileUploadLike(Protocol):
    filename: str | None

    def save(self, dst: str | Path) -> None: ...


@runtime_checkable
class FileMapLike(Protocol):
    def get(self, key: str) -> FileUploadLike | None: ...


@runtime_checkable
class RequestLike(Protocol):
    path: str
    method: str
    args: QueryArgsLike
    form: FormLike
    files: FileMapLike
    cookies: CookieMapLike


@runtime_checkable
class ResponseLike(Protocol):
    status_code: int
    content_type: str
    headers: dict[str, str]

    def set_data(self, data: str | bytes) -> None: ...

    def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int | None = None,
        path: str = "/",
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "Lax",
    ) -> None: ...

    def delete_cookie(self, key: str, path: str = "/") -> None: ...


@dataclass(frozen=True, slots=True)
class StatusReplacements:
    text: str
    css_class: str
    hidden_attr: str


def status_hidden() -> StatusReplacements:
    return StatusReplacements("", "", "hidden")


def status_visible(text: str, css_class: str) -> StatusReplacements:
    return StatusReplacements(text, css_class, "")


def status_for_message(msg: str, mapping: dict[str, StatusReplacements]) -> StatusReplacements:
    normalized_msg = msg.strip()
    if not normalized_msg:
        return status_hidden()
    return mapping.get(normalized_msg, status_hidden())
