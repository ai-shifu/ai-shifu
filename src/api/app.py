"""Create and run the Flask application."""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flaskr.framework.plugin.plugin_manager import (
    enable_plugin_manager,
    get_plugin_manager,
)

# set timezone to UTC
# fix windows platform
if os.name == "nt":
    # tzutil ships with Windows and is resolved from PATH.
    subprocess.run(["tzutil", "/s", "UTC"], check=False)  # noqa: S607
else:
    # Load environment variables first so we can use get_config
    if not os.getenv("SKIP_LOAD_DOTENV"):
        load_dotenv()
    from flaskr.common.config import get_config

    timezone = get_config("TZ")
    # This must stay a direct env write: time.tzset() reads the process TZ
    # environment variable, and it has to run at import time, before the
    # Flask app (and the registry-backed config instance) exists.
    os.environ["TZ"] = timezone
    time.tzset()


@dataclass(slots=True)
class _ApplicationState:
    app: Flask | None = None


_application_state = _ApplicationState()
app: Flask | None = None


def create_app() -> Flask:
    if _application_state.app is not None:
        return _application_state.app
    import pymysql

    pymysql.install_as_MySQLdb()
    flask_app = Flask(__name__, instance_relative_config=True)
    CORS(
        flask_app,
        resources={
            r"/api/*": {
                "origins": [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ],
                "allow_headers": "*",
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            }
        },
        supports_credentials=True,
    )
    from flaskr.common import Config, init_log
    from flaskr.common.observability import init_observability

    flask_app.config = Config(flask_app.config, flask_app)

    # init observability before request logging so trace ids are available in logs
    init_observability(flask_app)
    # init log
    init_log(flask_app)
    flask_app = enable_plugin_manager(flask_app)
    flask_app.logger.info("ai-shifu-api mode: %s", flask_app.config.get("MODE", "api"))
    # init database
    from flaskr import dao

    dao.init_db(flask_app)

    # init i18n
    from flaskr.i18n import load_translations

    load_translations(flask_app)

    # init redis
    dao.init_redis(flask_app)

    from flaskr.service.user.auth import register_builtin_providers

    register_builtin_providers()

    # Init LLM
    with flask_app.app_context():
        from flaskr.api import llm  # noqa: F401
    # init langfuse
    from flaskr import api

    api.init_langfuse(flask_app)
    # load plugins
    from flaskr.framework.plugin.load_plugin import load_plugins_from_dir

    plugin_manager = get_plugin_manager()
    if plugin_manager is None:
        raise RuntimeError("Plugin manager is not enabled")

    load_plugins_from_dir(flask_app, str(Path("flaskr") / "service"))
    try:
        load_plugins_from_dir(
            flask_app, str(Path("flaskr") / "plugins"), plugin_manager
        )
    except Exception as e:
        flask_app.logger.warning("load plugins error: %s", e)

    Migrate(flask_app, dao.db)
    # register route
    from flaskr.route import register_route

    flask_app = register_route(flask_app)
    # init swagger
    if flask_app.config.get("SWAGGER_ENABLED", False):
        from flaskr.common import sanitize_swagger_docstring, swagger_config

        flask_app.logger.info("swagger init ...")
        Swagger(
            flask_app,
            config=swagger_config,
            sanitizer=sanitize_swagger_docstring,
            merge=True,
        )

    # enable hot reload
    if flask_app.config.get("ENV") == "development":
        plugin_manager.enable_hot_reload()

    _application_state.app = flask_app
    return flask_app


if __name__ == "__main__":
    app = create_app()
    # Only enable debug mode if explicitly running in development environment
    # Binding to all interfaces is required for the containerized dev server.
    app.run(host="0.0.0.0", port=5800, debug=app.config.get("ENV") == "development")  # noqa: S104
elif not os.getenv("SKIP_APP_AUTOCREATE"):
    app = create_app()
    from flaskr.framework.plugin.enable_plugin import enable_plugins

    enable_plugins(app)
    from flaskr.command import enable_commands

    enable_commands(app)
