def as_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def as_int_or_none(value: object | None, *, allow_bool: bool = True) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value) if allow_bool else None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def as_int(value: object, default: int = 0, *, allow_bool: bool = True) -> int:
    parsed = as_int_or_none(value, allow_bool=allow_bool)
    return parsed if parsed is not None else default


def as_float_or_none(value: object | None, *, allow_bool: bool = True) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value) if allow_bool else None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def as_float(value: object, default: float = 0.0, *, allow_bool: bool = True) -> float:
    parsed = as_float_or_none(value, allow_bool=allow_bool)
    return parsed if parsed is not None else default
