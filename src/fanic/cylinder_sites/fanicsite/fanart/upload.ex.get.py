from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.common import text_error
from fanic.cylinder_sites.fanicsite.fanart.upload_page import render_upload_page


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/fanart/upload":
        return text_error(response, "Not found", 404)
    return render_upload_page(request, response)
