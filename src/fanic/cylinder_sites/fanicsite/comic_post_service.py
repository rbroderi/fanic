def csv_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def is_explicit_rating(value: object) -> bool:
    return str(value).strip().casefold() == "explicit"


def parse_series_index(raw_value: str) -> int | None:
    text = raw_value.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def normalize_status(raw_value: str) -> str:
    status = raw_value.strip()
    if status not in {"in_progress", "complete"}:
        return "in_progress"
    return status


def normalize_language(raw_value: str) -> str:
    text = raw_value.strip()
    return text if text else "en"


def resolve_title(raw_title: str, existing_title: object) -> str:
    text = raw_title.strip()
    if text:
        return text
    fallback = str(existing_title).strip()
    return fallback if fallback else "Untitled"


def resolve_rating(raw_rating: str) -> str:
    text = raw_rating.strip()
    return text if text else "Not Rated"


def should_lock_explicit_demotion(
    *,
    is_admin: bool,
    current_rating: object,
    requested_rating: object,
) -> bool:
    return (not is_admin) and is_explicit_rating(current_rating) and (not is_explicit_rating(requested_rating))


def build_metadata_from_form(
    *,
    existing_title: object,
    title_raw: str,
    summary_raw: str,
    rating_raw: str,
    warnings_raw: str,
    status_raw: str,
    language_raw: str,
    series_raw: str,
    series_index_raw: str,
    published_at_raw: str,
    fandoms_raw: str,
    relationships_raw: str,
    characters_raw: str,
    freeform_tags_raw: str,
) -> dict[str, object]:
    return {
        "title": resolve_title(title_raw, existing_title),
        "summary": summary_raw.strip(),
        "rating": resolve_rating(rating_raw),
        "warnings": csv_values(warnings_raw),
        "status": normalize_status(status_raw),
        "language": normalize_language(language_raw),
        "series": series_raw.strip(),
        "series_index": parse_series_index(series_index_raw),
        "published_at": published_at_raw.strip(),
        "fandoms": csv_values(fandoms_raw),
        "relationships": csv_values(relationships_raw),
        "characters": csv_values(characters_raw),
        "freeform_tags": csv_values(freeform_tags_raw),
    }
