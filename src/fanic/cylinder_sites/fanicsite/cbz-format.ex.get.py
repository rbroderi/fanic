from __future__ import annotations

from fanic.cylinder_sites.common import (
    RequestLike,
    ResponseLike,
    render_html_template,
    text_error,
)


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/cbz-format":
        return text_error(response, "Not found", 404)
    return render_html_template(request, response, "cbz-format.html")
