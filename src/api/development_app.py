# ruff: noqa: INP001 - WSGI entry beside app.py; src/api must not become a package.
"""Explicit local/test WSGI entry; never use this module for deployments."""

import os

# The normal module auto-creates a strict app on import. Defer only that side
# effect so the dedicated entry grants its capability before initialization.
_previous_skip = os.environ.get("SKIP_APP_AUTOCREATE")
os.environ["SKIP_APP_AUTOCREATE"] = "1"
try:
    import app as application
finally:
    if _previous_skip is None:
        os.environ.pop("SKIP_APP_AUTOCREATE", None)
    else:
        os.environ["SKIP_APP_AUTOCREATE"] = _previous_skip

app = application.create_app(development_verification_codes=True)
# Gunicorn's existing post-fork initialization uses the normal module's app.
application.app = app
app.logger.warning("Development verification-code entry enabled; local/test use only")

from flaskr.command import enable_commands  # noqa: E402 - needs the initialized app
from flaskr.framework.plugin.enable_plugin import (  # noqa: E402
    enable_plugins,
)

enable_plugins(app)
enable_commands(app)
