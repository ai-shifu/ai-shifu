from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from pymilvus import MilvusClient
from sqlalchemy import event
import sqlparse
import logging


def init_db(app: Flask):
    global db
    app.logger.info("init db")
    if (
        app.config.get("MYSQL_HOST", None) is not None
        and app.config.get("MYSQL_PORT", None) is not None
        and app.config.get("MYSQL_DB", None) is not None
        and app.config["MYSQL_USER"] is not None
        and app.config.get("MYSQL_PASSWORD") is not None
    ):
        app.logger.info("init dbconfig from env")
        app.config["SQLALCHEMY_DATABASE_URI"] = (
            "mysql://"
            + app.config["MYSQL_USER"]
            + ":"
            + app.config["MYSQL_PASSWORD"]
            + "@"
            + app.config["MYSQL_HOST"]
            + ":"
            + str(app.config["MYSQL_PORT"])
            + "/"
            + app.config["MYSQL_DB"]
        )
    else:
        app.logger.info("init dbconfig from config")

    if app.debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    db = SQLAlchemy()
    db.init_app(app)

    # Enable formatted SQL output in the development environment
    if app.debug:

        def setup_sql_logging():
            @event.listens_for(db.engine, "before_cursor_execute")
            def before_cursor_execute(
                conn, cursor, statement, parameters, context, executemany
            ):
                # Format the SQL statement
                formatted_sql = sqlparse.format(
                    statement, reindent=True, keyword_case="upper", strip_comments=True
                )

                # If there are parameters, try formatting
                if parameters:
                    try:
                        # Try to format the parameters into the SQL statement
                        raw_sql = formatted_sql % parameters
                    except (TypeError, ValueError):
                        # If the formatting fails, the SQL and parameters will be displayed respectively
                        raw_sql = f"SQL:\n{formatted_sql}\nParameters: {parameters}"
                else:
                    raw_sql = formatted_sql

                app.logger.info(f"\n{raw_sql}\n")

        # Set the event listener in the application context
        with app.app_context():
            setup_sql_logging()


def init_redis(app: Flask):
    global redis_client
    app.logger.info(
        "init redis {} {} {}".format(
            app.config["REDIS_HOST"], app.config["REDIS_PORT"], app.config["REDIS_DB"]
        )
    )
    if app.config["REDIS_PASSWORD"] is not None and app.config["REDIS_PASSWORD"] != "":
        redis_client = Redis(
            host=app.config["REDIS_HOST"],
            port=app.config["REDIS_PORT"],
            db=app.config["REDIS_DB"],
            password=app.config["REDIS_PASSWORD"],
            username=app.config.get("REDIS_USER", None),
        )
    else:
        redis_client = Redis(
            host=app.config["REDIS_HOST"],
            port=app.config["REDIS_PORT"],
            db=app.config["REDIS_DB"],
        )
    app.logger.info("init redis done")


def run_with_redis(app, key, timeout: int, func, args):
    with app.app_context():
        app.logger.info("run_with_redis start {}".format(key))
        lock = redis_client.lock(key, timeout=timeout, blocking_timeout=timeout)
        if lock.acquire(blocking=False):
            app.logger.info("run_with_redis get lock {}".format(key))
            try:
                return func(*args)
            finally:
                lock.release()
        else:
            app.logger.info("run_with_redis get lock failed {}".format(key))
            return None


def init_milvus(app: Flask):
    global milvus_client
    if (
        app.config.get("MILVUS_URI") is not None
        and app.config.get("MILVUS_TOKEN") is not None
        and app.config.get("MILVUS_DB_NAME") is not None
    ):
        milvus_client = MilvusClient(
            uri=app.config.get("MILVUS_URI"),
            token=app.config.get("MILVUS_TOKEN"),
            db_name=app.config.get("MILVUS_DB_NAME"),
        )
        app.logger.info("init milvus done")
    else:
        milvus_client = None
        app.logger.warning("init milvus failed")
