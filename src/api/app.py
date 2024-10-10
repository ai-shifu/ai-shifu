import os
import time
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from flask_migrate import Migrate
from flasgger import Swagger


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
    # init database
    from flaskr import dao

    dao.init_db(app)
    # init models and migrate
    # from flaskr.service.admin.models import AdminUser
    Migrate(app, dao.db)

    # init redis
    dao.init_redis(app)

    # init langfuse
    from flaskr import api

    api.init_langfuse(app)

    # load plugins
    from flaskr.util.plugin import load_plugins_from_dir

    load_plugins_from_dir(app, "flaskr/service/study/input")
    load_plugins_from_dir(app, "flaskr/service/study/ui")
    # register route
    from flaskr.route import register_route

    app = register_route(app)
    # init swagger
    if app.config.get("SWAGGER_ENABLED", False):
        from flaskr.common import swagger_config

        app.logger.info("swagger init ...")
        Swagger(app, config=swagger_config, merge=True)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5800, debug=True)
else:
    app = create_app()
