from __future__ import annotations

from fanic.cylinder_main import create_app, serve, startup

# Keep a module-level app object for server tooling compatibility.
app = create_app()

__all__ = ["app", "create_app", "serve", "startup"]
