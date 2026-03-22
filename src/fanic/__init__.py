from __future__ import annotations

import logging

from fanic.settings import get_settings

if get_settings().enable_beartype:
    from beartype.claw import beartype_this_package

    logging.getLogger(__name__).info(
        "Enabling beartype runtime type checking for fanic"
    )
    beartype_this_package()

__all__ = ["__version__"]

__version__ = "0.1.0"
