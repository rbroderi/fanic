from fanic.settings import FanicSettings


def resolve_thumbnail_dimensions(settings: FanicSettings) -> tuple[int, int]:
    return settings.thumbnail_max_dimensions


def image_processing_constants(settings: FanicSettings) -> tuple[int, int, int]:
    return (
        settings.image_avif_quality,
        settings.thumbnail_avif_quality,
        settings.max_upload_image_pixels,
    )
