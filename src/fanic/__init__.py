from __future__ import annotations

import logging
import os

if os.getenv("FANIC_ENABLE_BEARTYPE", "1") != "0":
    from beartype.claw import beartype_this_package

    logging.getLogger(__name__).info(
        "Enabling beartype runtime type checking for fanic"
    )
    beartype_this_package()

__all__ = ["__version__"]

__version__ = "0.1.0"
