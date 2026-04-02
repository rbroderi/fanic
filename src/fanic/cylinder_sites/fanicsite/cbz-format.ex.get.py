from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import render_html_template
from fanic.cylinder_sites.common.responses import text_error


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/cbz-format":
        return text_error(response, "Not found", 404)
    return render_html_template(request, response, "cbz-format.html")
