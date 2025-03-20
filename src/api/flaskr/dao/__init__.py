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
    # app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    # "pool_size": 20,
    # "max_overflow": 20,
    # "pool_timeout": 60,
    # "pool_recycle": 3600,
    # "pool_pre_ping": True,
    # "echo": True,                # 打印SQL语句，用于调试
    # "echo_pool": True,          # 打印连接池事件
    # "connect_args": {           # 特定数据库的连接参数
    #     "connect_timeout": 10,
    #     "charset": "utf8mb4"
    # }
    # }
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
