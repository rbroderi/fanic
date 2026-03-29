from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import render_html_template
from fanic.cylinder_sites.common import text_error


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/account/logged-out":
        return text_error(response, "Not found", 404)

    return render_html_template(
        request,
        response,
        "logged-out.html",
    )
