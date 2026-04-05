from fanic.cylinder_sites.common.protocols import RequestLike
from fanic.cylinder_sites.common.protocols import ResponseLike
from fanic.cylinder_sites.common.responses import redirect_see_other as _redirect
from fanic.cylinder_sites.common.responses import text_error
from fanic.settings import get_settings


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/support":
        return text_error(response, "Not found", 404)

    support_url = get_settings().buymeacoffee_page_url.strip()
    target = support_url if support_url else "https://buymeacoffee.com/fanic.media"
    return _redirect(response, target)
