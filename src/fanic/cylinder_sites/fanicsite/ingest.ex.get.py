from __future__ import annotations

from fanic.cylinder_sites.common import RequestLike, ResponseLike, text_error
from fanic.cylinder_sites.ingest_page import render_ingest_page


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/ingest":
        return text_error(response, "Not found", 404)
    return render_ingest_page(request, response)
