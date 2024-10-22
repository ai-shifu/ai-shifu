from multiprocessing import Process
import time


def worker(app, i):
    from flaskr.dao import run_with_redis

    app.logger.info("{} start".format(i))
    time.sleep(1)
    app.logger.info("{} end".format(i))
    return run_with_redis(app, "test", 10, func, [i])


def func(i):
    return 1


def test_redis_lock(app):

    threads = []
    for i in range(10):
        app.logger.info("init {}".format(i))
        p = Process(target=worker, args=(app, i))
        threads.append(p)
        p.start()

    for p in threads:
        p.join()

    app.logger.info("done")
