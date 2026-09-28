"""Verify Skill identity follows only its device-issued token in Redis."""

from flaskr.service.common import session_attribution
from flaskr.service.common.skill_attribution import SkillIdentityInput

from tests.common.fixtures.fake_redis import FakeRedis


def test_session_attribution_round_trips_and_renews_ttl(
    app: object, monkeypatch: object
) -> None:
    fake_cache = FakeRedis()
    monkeypatch.setattr(session_attribution, "cache", fake_cache)
    monkeypatch.setitem(app.config, "TOKEN_EXPIRE_TIME", 120)
    identity = SkillIdentityInput(
        host_platform="doubao",
        skill_id="ai-shifu-course-creator",
        skill_version="3.1.4",
    )

    session_attribution.save_session_skill_attribution(
        app, token="secret-token", attribution=identity
    )
    loaded = session_attribution.get_session_skill_attribution(
        app, token="secret-token"
    )

    assert loaded == identity
    key = session_attribution._cache_key(app, "secret-token")
    assert "secret-token" not in key
    assert fake_cache.ttl(key) > 0


def test_corrupt_or_unavailable_attribution_never_blocks_business_flow(
    app: object, monkeypatch: object
) -> None:
    fake_cache = FakeRedis()
    monkeypatch.setattr(session_attribution, "cache", fake_cache)
    key = session_attribution._cache_key(app, "secret-token")
    fake_cache.set(key, "not-json", ex=60)

    assert (
        session_attribution.get_session_skill_attribution(app, token="secret-token")
        is None
    )
    assert fake_cache.get(key) is None

    class BrokenCache:
        def getex(self, *_args: object, **_kwargs: object) -> None:
            raise TimeoutError

        def delete(self, *_args: object, **_kwargs: object) -> None:
            raise TimeoutError

    monkeypatch.setattr(session_attribution, "cache", BrokenCache())
    assert (
        session_attribution.get_session_skill_attribution(app, token="secret-token")
        is None
    )


def test_active_session_refresh_renews_attribution_ttl(
    app: object, monkeypatch: object
) -> None:
    fake_cache = FakeRedis()
    monkeypatch.setattr(session_attribution, "cache", fake_cache)
    monkeypatch.setitem(app.config, "TOKEN_EXPIRE_TIME", 120)
    identity = SkillIdentityInput(
        host_platform="direct",
        skill_id="ai-shifu-course-creator",
        skill_version="2.0.0",
    )
    session_attribution.save_session_skill_attribution(
        app, token="active-token", attribution=identity
    )
    key = session_attribution._cache_key(app, "active-token")
    fake_cache._expires[key] = fake_cache._now() + 1

    session_attribution.touch_session_skill_attribution(app, token="active-token")

    assert fake_cache.ttl(key) > 100
