from types import SimpleNamespace

import flaskr.dao as dao
from flaskr.service.billing import admin_ops_state


class _TrackingLock:
    def __init__(self, events, key):
        self._events = events
        self._key = key

    def acquire(self, **_kwargs):
        self._events.append(("acquire", self._key))
        return True

    def release(self):
        self._events.append(("release", self._key))


class _TrackingRedis:
    def __init__(self):
        self.events = []

    def lock(self, key, **_kwargs):
        self.events.append(("lock", key))
        return _TrackingLock(self.events, key)


class _FakeSaasFuncs:
    def __init__(self):
        self.store = {}
        self.SaasUserConfigCreateDTO = SimpleNamespace

    def get_sass_config(self, user_bid, key, default=""):
        return self.store.get((user_bid, key), default)

    def create_or_update_saas_user_config(self, _app, payload):
        self.store[(payload.user_bid, payload.key)] = payload.value
        self.store[(payload.user_bid, payload.key, "is_encrypted")] = (
            payload.is_encrypted
        )
        return payload


def test_admin_billing_ops_state_updates_under_redis_lock(app, monkeypatch):
    redis = _TrackingRedis()
    fake_saas = _FakeSaasFuncs()
    monkeypatch.setattr(dao, "redis_client", redis, raising=False)
    monkeypatch.setattr(admin_ops_state, "_saas_funcs", lambda **_kwargs: fake_saas)

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
    assert (
        fake_saas.store[
            (
                "billing-admin-ops",
                "ADMIN_BILLING.CONFIG_STATUS",
                "is_encrypted",
            )
        ]
        == 0
    )
    assert redis.events == [
        ("lock", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
        ("acquire", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
        ("release", "billing:admin_ops_state:ADMIN_BILLING.CONFIG_STATUS"),
    ]


def test_admin_billing_exception_handled_state_persists_without_encryption(
    app, monkeypatch
):
    redis = _TrackingRedis()
    fake_saas = _FakeSaasFuncs()
    monkeypatch.setattr(dao, "redis_client", redis, raising=False)
    monkeypatch.setattr(admin_ops_state, "_saas_funcs", lambda **_kwargs: fake_saas)

    result = admin_ops_state.update_admin_billing_exception_handled(
        app,
        row_key="subscription:sub-past-due",
        handled=True,
    )

    assert result == {"row_key": "subscription:sub-past-due", "handled": True}
    assert admin_ops_state.build_admin_billing_ops_state(app)["exception_handled"] == {
        "subscription:sub-past-due": True
    }
    assert (
        fake_saas.store[
            (
                "billing-admin-ops",
                "ADMIN_BILLING.EXCEPTION_HANDLED",
                "is_encrypted",
            )
        ]
        == 0
    )

    admin_ops_state.update_admin_billing_exception_handled(
        app,
        row_key="subscription:sub-past-due",
        handled=False,
    )

    assert admin_ops_state.build_admin_billing_ops_state(app)["exception_handled"] == {}
