from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import json_response
from fanic.cylinder_sites.common import text_error
from fanic.db import get_connection


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/api/health":
        return text_error(response, "Not found", 404)

    try:
        with get_connection() as connection:
            row = connection.execute("SELECT 1").fetchone()
            db_ok = row is not None
    except Exception:
        db_ok = False

    status_code = 200 if db_ok else 503
    return json_response(
        response,
        {"ok": db_ok, "service": "fanic", "db": "up" if db_ok else "down"},
        status_code,
    )
