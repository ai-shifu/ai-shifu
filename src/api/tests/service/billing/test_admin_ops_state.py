"""Verify admin ops state behavior."""

from flaskr import dao
from flaskr.service.billing import admin_ops_state


class _TrackingLock:
    def __init__(self, events: object, key: object) -> None:
        self._events = events
        self._key = key

    def acquire(self, **_kwargs: object):
        self._events.append(("acquire", self._key))
        return True

    def release(self):
        self._events.append(("release", self._key))


class _TrackingRedis:
    def __init__(self) -> None:
        self.events = []

    def lock(self, key: object, **_kwargs: object):
        self.events.append(("lock", key))
        return _TrackingLock(self.events, key)


def _patch_config_store(monkeypatch: object):
    store = {}

    def fake_get_config(key: object, default: object = None):
        return store.get(key, default)

    def fake_update_config(_app: object, key: object, value: object, **kwargs: object):
        store[key] = value
        store[(key, "meta")] = kwargs
        return True

    monkeypatch.setattr(admin_ops_state, "get_config", fake_get_config)
    monkeypatch.setattr(admin_ops_state, "update_config", fake_update_config)
    return store


def test_admin_billing_ops_state_updates_under_redis_lock(
    app: object, monkeypatch: object
):
    redis = _TrackingRedis()
    store = _patch_config_store(monkeypatch)
    monkeypatch.setattr(dao._redis_state, "client", redis)

    admin_ops_state.update_admin_billing_config_status(
        app,
        creator_bid="creator-ops-1",
        payload={"status": "completed", "note": "checked"},
    )

    state = admin_ops_state.build_admin_billing_ops_state(app)
    assert state["config_status"]["creator-ops-1"] == {
        "status": "completed",
        "note": "checked",
    }
    assert store[("ADMIN_BILLING.CONFIG_STATUS", "meta")] == {
        "is_secret": False,
        "remark": "Admin billing operations state",
        "updated_by": "billing-admin-ops",
    }
    assert redis.events == [
        ("lock", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
        ("acquire", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
        ("release", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
    ]
