import fanic.cylinder_sites.common.responses as common
from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/theme/custom.css":
        return common.text_error(response, "Not found", 404)

    css_text = common.custom_theme_css_text(request)
    response.status_code = 200
    response.content_type = "text/css; charset=utf-8"
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.set_data(css_text)
    return response
