from fanic.cylinder_sites.common import RequestLike
from fanic.cylinder_sites.common import ResponseLike
from fanic.cylinder_sites.fanicsite.users import ex_get_handler


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    return ex_get_handler.main(request, response)
