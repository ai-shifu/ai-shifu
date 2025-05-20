import os
import time
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_migrate import Migrate
from flasgger import Swagger
from flaskr.framework.plugin.plugin_manager import enable_plugin_manager

# set timezone to UTC
# fix windows platform
if os.name == "nt":
    os.system('tzutil /s "UTC"')
else:
    os.environ["TZ"] = "UTC"
    time.tzset()
app = None


def create_app() -> Flask:
    global app
    if app:
        return app
    import pymysql

    pymysql.install_as_MySQLdb()
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    CORS(app, resources={r"/*": {"supports_credentials": True}})
    from flaskr.common import Config, init_log

    app.config = Config(app.config, app)

    # init log
    init_log(app)
    app = enable_plugin_manager(app)
    app.logger.info("ai-shifu-api mode: %s", app.config.get("MODE", "api"))
    # init database
    from flaskr import dao

    dao.init_db(app)

    # init i18n
    from flaskr.i18n import load_translations

    load_translations(app)

    # init redis
    dao.init_redis(app)

    # init milvus
    dao.init_milvus(app)

    # Init LLM
    with app.app_context():
        from flaskr.api import llm  # noqa
    # init langfuse
    from flaskr import api

    api.init_langfuse(app)
    # load plugins
    from flaskr.framework.plugin.load_plugin import load_plugins_from_dir
    from flaskr.framework.plugin.plugin_manager import plugin_manager

    load_plugins_from_dir(app, os.path.join("flaskr", "service"))
    try:
        load_plugins_from_dir(app, os.path.join("flaskr", "plugins"), plugin_manager)
    except Exception as e:
        app.logger.warning(f"load plugins error: {e}")

    Migrate(app, dao.db)
    # register route
    from flaskr.route import register_route

    app = register_route(app)
    # init swagger
    if app.config.get("SWAGGER_ENABLED", False):
        from flaskr.common import swagger_config

        app.logger.info("swagger init ...")
        Swagger(app, config=swagger_config, merge=True)

    # enable hot reload
    if app.config.get("ENV") == "development":
        plugin_manager.enable_hot_reload()
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5800, debug=True)
else:
    app = create_app()
    from flaskr.framework.plugin.enable_plugin import enable_plugins

    enable_plugins(app)
    from flaskr.command import enable_commands

    enable_commands(app)
