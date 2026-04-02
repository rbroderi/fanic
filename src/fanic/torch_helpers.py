from typing import Any


def call0(obj: object | None, name: str) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member()
    except Exception:
        return None


def call1(obj: object | None, name: str, arg1: object) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member(arg1)
    except Exception:
        return None


def call_kw(
    obj: object | None,
    name: str,
    *args: object,
    **kwargs: object,
) -> object | None:
    if obj is None:
        return None
    member = getattr(obj, name, None)
    if not callable(member):
        return None
    try:
        return member(*args, **kwargs)
    except Exception:
        return None


def call0_context_manager(obj: object | None, name: str) -> Any | None:
    value = call0(obj, name)
    if value is None:
        return None
    enter = getattr(value, "__enter__", None)
    exit_ = getattr(value, "__exit__", None)
    if not callable(enter) or not callable(exit_):
        return None
    return value
