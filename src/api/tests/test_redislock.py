from threading import Thread
import time
import pytest
from flask import Flask
from flaskr import dao


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["REDIS_MOCK"] = "true"
    dao.init_redis(app)
    return app


def worker(app, i):
    from flaskr.dao import run_with_redis

    app.logger.info(f"{i} start")
    time.sleep(1)
    app.logger.info(f"{i} end")
    return run_with_redis(app, "test", 10, func, [i])


def func(i):
    return 1


def test_redis_lock(app):
    threads = []
    for i in range(10):
        app.logger.info(f"init {i}")
        t = Thread(target=worker, args=(app, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    app.logger.info("done")
