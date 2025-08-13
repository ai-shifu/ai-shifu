from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from pymilvus import MilvusClient
from sqlalchemy import event
import sqlparse
import logging
import traceback
import os


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
                stack = traceback.extract_stack()
                project_root = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), "../../../")
                )
                caller_info = "Unknown location"

                for frame in reversed(stack[:-2]):
                    if (
                        project_root in frame.filename
                        and "site-packages" not in frame.filename
                    ):
                        caller_info = f"File: {os.path.relpath(frame.filename, project_root)}, Line: {frame.lineno}, Function: {frame.name}"
                        break

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

                app.logger.info(f"\nLocation: {caller_info}\n{raw_sql}\n")

        # Set the event listener in the application context
        with app.app_context():
            setup_sql_logging()


def init_redis(app: Flask):
    global redis_client
    # Use an in-memory Redis when REDIS_MOCK is enabled. This is helpful for running
    # tests without requiring an actual Redis service.
    if str(app.config.get("REDIS_MOCK", "false")).lower() == "true":
        try:
            import fakeredis

            redis_client = fakeredis.FakeRedis()
        except ModuleNotFoundError:
            from threading import Lock

            class _SimpleRedis:
                def __init__(self):
                    self.store = {}
                    self.locks = {}

                def get(self, key):
                    return self.store.get(key)

                def set(self, key, value, ex=None):
                    self.store[key] = value

                def delete(self, key):
                    self.store.pop(key, None)

                def ttl(self, key):
                    return None

                def incr(self, key):
                    self.store[key] = int(self.store.get(key, 0)) + 1
                    return self.store[key]

                def lock(self, key, timeout=None, blocking_timeout=None):
                    return self.locks.setdefault(key, Lock())

            redis_client = _SimpleRedis()

        app.logger.info("init fakeredis done")
        return

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
                try:
                    lock.release()
                except Exception:
                    pass
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
