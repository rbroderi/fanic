from fanic.cylinder_sites.common import RequestLike, ResponseLike, text_error


def main(request: RequestLike, response: ResponseLike) -> ResponseLike:
    if request.path != "/update":
        return text_error(response, "Not found", 404)
    response.status_code = 302
    response.content_type = "text/plain; charset=utf-8"
    response.headers["Location"] = "/ingest"
    response.set_data("Redirecting to /ingest")
    return response
