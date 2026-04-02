from typing import cast


def resolve_thumbnail_dimensions(settings: object) -> tuple[int, int]:
    dims_obj: object = getattr(settings, "thumbnail_max_dimensions", (720, 720))
    if isinstance(dims_obj, tuple):
        dims_tuple = cast(tuple[object, ...], dims_obj)
        if len(dims_tuple) == 2:
            width_obj, height_obj = dims_tuple
            if isinstance(width_obj, int) and isinstance(height_obj, int):
                return (width_obj, height_obj)
    return (720, 720)


def image_processing_constants(settings: object) -> tuple[int, int, int]:
    image_quality_obj: object = getattr(settings, "image_avif_quality", 75)
    thumb_quality_obj: object = getattr(settings, "thumbnail_avif_quality", 60)
    max_pixels_obj: object = getattr(settings, "max_upload_image_pixels", 40000000)

    image_quality = image_quality_obj if isinstance(image_quality_obj, int) else 75
    thumb_quality = thumb_quality_obj if isinstance(thumb_quality_obj, int) else 60
    max_pixels = max_pixels_obj if isinstance(max_pixels_obj, int) else 40000000
    return (image_quality, thumb_quality, max_pixels)
