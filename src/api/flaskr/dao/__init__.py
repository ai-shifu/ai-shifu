from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from redis import Redis


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
    db = SQLAlchemy()
    db.init_app(app)


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
        global redis_client
        app.logger.info("run_with_redis start {}".format(key))
        
        redis_timeout = min(timeout, 30)
        blocking_timeout = 3
        
        lock = redis_client.lock(key, timeout=redis_timeout, blocking_timeout=blocking_timeout)
        
        try:
            if lock.acquire(blocking=True):
                app.logger.info("run_with_redis get lock {}".format(key))
                try:
                    return func(*args)
                except Exception as e:
                    app.logger.error(f"Error in run_with_redis function execution: {str(e)}")
                    raise
                finally:
                    if hasattr(lock, 'owned') and lock.owned():
                        lock.release()
                        app.logger.info("run_with_redis release lock {}".format(key))
            else:
                app.logger.warning("run_with_redis get lock failed {}".format(key))
                return func(*args)
        except Exception as e:
            app.logger.error(f"Error in run_with_redis lock operation: {str(e)}")
            if lock and hasattr(lock, 'owned') and lock.owned():
                lock.release()
                app.logger.info("run_with_redis release lock in exception {}".format(key))
            return func(*args)
