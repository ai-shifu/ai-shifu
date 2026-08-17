"""Celery worker children must not reuse the parent's pooled connections.

The celery parent builds the Flask app (validating a DB connection on the
way); billiard then forks worker children which inherit the pool with the
parent's open sockets. Production journals showed one connection checked
out by pid=1 and then by two different worker pids on the same MySQL
server thread id - concurrent children interleaving one socket is the
off-by-one protocol desync. The worker_process_init hook must discard the
inherited pool without touching the parent's file descriptors.
"""

from celery.signals import worker_process_init
from flaskr.common.celery_app import dispose_inherited_db_pools, get_celery_app
from flaskr.dao import db
from sqlalchemy import text


def test_dispose_replaces_the_inherited_pool(app):
    with app.app_context():
        db.session.execute(text("SELECT 1"))
        db.session.remove()
        inherited_pool = db.engine.pool

    dispose_inherited_db_pools(app)

    with app.app_context():
        assert db.engine.pool is not inherited_pool
        # The replacement pool must be immediately usable.
        db.session.execute(text("SELECT 1"))
        db.session.remove()


def test_worker_process_init_signal_disposes_pools(app):
    get_celery_app(app)
    with app.app_context():
        db.session.execute(text("SELECT 1"))
        db.session.remove()
        inherited_pool = db.engine.pool

    worker_process_init.send(sender=None)

    with app.app_context():
        assert db.engine.pool is not inherited_pool


def test_one_failing_bind_does_not_block_the_rest(app, monkeypatch):
    import flaskr.dao as dao

    disposed = []

    class _BrokenEngine:
        def dispose(self, close):
            raise RuntimeError("bind gone")

    class _GoodEngine:
        def dispose(self, close):
            disposed.append(close)

    class _FakeDB:
        engines = {"broken": _BrokenEngine(), None: _GoodEngine()}

    monkeypatch.setattr(dao, "db", _FakeDB())

    dispose_inherited_db_pools(app)

    assert disposed == [False]
