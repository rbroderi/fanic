from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import json_response
from fanic.cylinder_sites.common.responses import text_error
from fanic.db import get_connection
from fanic.moderation import get_moderation_sidecar_health
from fanic.storage_health import get_fanart_storage_health


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/api/health":
        return text_error(response, "Not found", 404)

    try:
        with get_connection() as connection:
            row = connection.execute("SELECT 1").fetchone()
            db_ok = row is not None
    except Exception:
        db_ok = False

    fanart_storage = "unknown"
    fanart_payload: dict[str, object] = {}
    if db_ok:
        try:
            fanart_health = get_fanart_storage_health(max_rows_to_check=50)
            fanart_storage = fanart_health.status
            fanart_payload = {
                "fanart_storage": fanart_storage,
                "fanart_db_items": fanart_health.db_items,
                "fanart_checked_items": fanart_health.checked_items,
                "fanart_missing_images": fanart_health.missing_image_files,
                "fanart_missing_thumbs": fanart_health.missing_thumb_files,
                "fanart_image_dir_exists": fanart_health.image_dir_exists,
                "fanart_thumb_dir_exists": fanart_health.thumb_dir_exists,
            }
        except Exception:
            fanart_storage = "down"
            fanart_payload = {"fanart_storage": fanart_storage}
    else:
        fanart_payload = {"fanart_storage": fanart_storage}

    moderation_payload = get_moderation_sidecar_health()
    moderation_sidecar = str(moderation_payload.get("moderation_sidecar", "disabled"))

    status_code = 200 if db_ok and fanart_storage != "down" and moderation_sidecar != "down" else 503
    return json_response(
        response,
        {
            "ok": db_ok and fanart_storage != "down" and moderation_sidecar != "down",
            "service": "fanic",
            "db": "up" if db_ok else "down",
            **fanart_payload,
            **moderation_payload,
        },
        status_code,
    )
