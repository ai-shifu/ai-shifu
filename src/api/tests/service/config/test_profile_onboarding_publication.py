"""Exercise actual JSON persistence and CAS with an isolated SQLite test database."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock
from unittest.mock import Mock

import pytest
from flaskr.dao import db, uow
from flaskr.i18n import get_i18n_list
from flaskr.service.common.models import AppError
from flaskr.service.config import profile_onboarding as module
from flaskr.service.config.models import Config


@pytest.fixture(autouse=True)
def stub_prompt_localizer(monkeypatch: object) -> None:
    from flaskr.service.common import profile_onboarding as config

    monkeypatch.setattr(
        config,
        "localize_profile_onboarding_assistant_prompt",
        lambda _app, prompt, *, target_locales=None: {
            locale: f"{locale}: {prompt}"
            for locale in (target_locales or get_i18n_list())
        },
    )


@pytest.fixture
def publication(app: object, monkeypatch: object) -> object:
    # Production uses MySQL GET_LOCK; SQLite has no advisory lock function.
    lock = Lock()

    @contextmanager
    def scoped_lock() -> object:
        with lock:
            yield

    monkeypatch.setattr(module, "_publication_lock", scoped_lock)
    monkeypatch.setattr(module, "redis", Mock())
    monkeypatch.setattr(module, "has_explicit_env_override", lambda _key: False)
    monkeypatch.setattr(module, "has_config_override", lambda _key: False)
    with app.app_context(), uow.unit_of_work():
        Config.query.filter(Config.key == module.CONFIG_KEY).delete()
    yield module
    with app.app_context(), uow.unit_of_work():
        Config.query.filter(Config.key == module.CONFIG_KEY).delete()


def test_initial_publication_rejects_second_stale_insert(
    app: object, publication: object
) -> None:
    assert publication.read_profile_onboarding_database(app) is None
    barrier = Barrier(2)

    def publish() -> bool:
        snapshot = publication.read_profile_onboarding_database(app)
        barrier.wait(timeout=5)
        try:
            publication.publish_profile_onboarding_database(
                app,
                expected_value=snapshot,
                value='{"revision":1}',
                updated_by="operator",
            )
        except AppError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(publish) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in futures) == [False, True]
    assert publication.read_profile_onboarding_database(app) == '{"revision":1}'
    with app.app_context():
        assert Config.query.filter(Config.key == module.CONFIG_KEY).count() == 1


def test_database_value_not_cached_revision_controls_publication(
    app: object, publication: object
) -> None:
    publication.publish_profile_onboarding_database(
        app, expected_value=None, value='{"revision":1}', updated_by="first"
    )
    old = publication.read_profile_onboarding_database(app)
    publication.publish_profile_onboarding_database(
        app, expected_value=old, value='{"revision":2}', updated_by="second"
    )
    with pytest.raises(AppError):
        publication.publish_profile_onboarding_database(
            app,
            expected_value=old,
            value='{"revision":2,"stale":true}',
            updated_by="first",
        )
    assert publication.read_profile_onboarding_database(app) == '{"revision":2}'


def test_cache_fault_after_commit_is_reported_as_durable(
    app: object, publication: object
) -> None:
    publication.redis.set.side_effect = RuntimeError("cache offline")
    publication.redis.delete.side_effect = RuntimeError("still offline")
    pending = publication.publish_profile_onboarding_database(
        app, expected_value=None, value='{"revision":1}', updated_by="operator"
    )
    assert pending is True
    assert publication.read_profile_onboarding_database(app) == '{"revision":1}'


def test_failed_database_commit_never_updates_cache(
    app: object, publication: object, monkeypatch: object
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    with monkeypatch.context() as patch:
        patch.setattr(
            db.session, "commit", Mock(side_effect=SQLAlchemyError("write failed"))
        )
        with pytest.raises(SQLAlchemyError):
            publication.publish_profile_onboarding_database(
                app, expected_value=None, value='{"revision":1}', updated_by="operator"
            )
    publication.redis.set.assert_not_called()
    assert publication.read_profile_onboarding_database(app) is None


def test_edit_during_localization_is_rejected(
    app: object, publication: object, monkeypatch: object
) -> None:
    from flaskr.service.common import profile_onboarding as config

    publication.publish_profile_onboarding_database(
        app,
        expected_value=None,
        value=(
            '{"revision":1,"markdownflow":"?[...Old answer]",'
            '"assistant_prompt":"Old prompt"}'
        ),
        updated_by="first",
    )
    old = publication.read_profile_onboarding_database(app)

    def localize_and_race(_app: object, prompt: str) -> object:
        publication.publish_profile_onboarding_database(
            app,
            expected_value=old,
            value='{"revision":2,"markdownflow":"?[Continue]"}',
            updated_by="second",
        )
        return {locale: f"{locale}: {prompt}" for locale in get_i18n_list()}

    monkeypatch.setattr(
        config, "localize_profile_onboarding_assistant_prompt", localize_and_race
    )
    with pytest.raises(AppError):
        config.update_profile_onboarding_config(
            app,
            payload={
                "enabled": True,
                "markdownflow": "?[...Answer]",
                "assistant_prompt": "Changed prompt",
                "config_revision": 1,
            },
            operator_user_bid="first",
        )
    assert (
        publication.read_profile_onboarding_database(app)
        == '{"revision":2,"markdownflow":"?[Continue]"}'
    )


def test_effective_read_ignores_stale_cache_after_publication(
    app: object, publication: object
) -> None:
    publication.publish_profile_onboarding_database(
        app,
        expected_value=None,
        value='{"revision":1,"assistant_prompt":"public"}',
        updated_by="operator",
    )
    publication.redis.get.return_value = '{"revision":0}'
    assert (
        publication.read_profile_onboarding_effective_value(app, "{}")
        == '{"revision":1,"assistant_prompt":"public"}'
    )


def test_nested_unit_of_work_cannot_report_an_uncommitted_save(
    app: object, publication: object
) -> None:
    with app.app_context(), uow.unit_of_work(), pytest.raises(AppError):
        publication.publish_profile_onboarding_database(
            app, expected_value=None, value='{"revision":1}', updated_by="operator"
        )
    publication.redis.set.assert_not_called()
    assert publication.read_profile_onboarding_database(app) is None


def test_publication_lock_timeout_does_not_enter_write_section(
    monkeypatch: object,
) -> None:
    connection = Mock()
    connection.execute.return_value.scalar.return_value = 0
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=connection)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(module, "db", Mock(engine=engine))
    entered = False
    with pytest.raises(AppError), module._publication_lock():
        entered = True
    assert entered is False
    assert connection.execute.call_count == 1


def test_publication_lock_cleanup_cannot_mask_completed_write(
    app: object, monkeypatch: object
) -> None:
    connection = Mock()
    connection.execute.side_effect = [
        Mock(scalar=Mock(return_value=1)),
        RuntimeError("connection lost"),
    ]
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=connection)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(module, "db", Mock(engine=engine))
    with app.app_context(), module._publication_lock():
        pass
    connection.invalidate.assert_called_once()


@pytest.mark.parametrize("cache_failure", [False, True])
def test_manual_assistant_prompt_uses_existing_durable_publication(
    app: object, publication: object, monkeypatch: object, cache_failure: bool
) -> None:
    import json

    from flaskr.service.common import profile_onboarding as config

    compiler = Mock()
    monkeypatch.setattr(config, "compile_profile_onboarding_assistant_prompt", compiler)
    if cache_failure:
        publication.redis.set.side_effect = RuntimeError("cache offline")
    result = config.update_profile_onboarding_config(
        app,
        payload={
            "enabled": True,
            "markdownflow": "?[...Answer]",
            "assistant_prompt": "  Operator wording  ",
        },
        operator_user_bid="operator",
    )
    saved = json.loads(publication.read_profile_onboarding_database(app))
    assert saved["assistant_prompt"] == "Operator wording"
    assert saved["markdownflow"] == "?[...Answer]"
    assert saved["revision"] == result["config_revision"] == 1
    assert bool(result.get("cache_refresh_pending")) is cache_failure
    compiler.assert_not_called()


def test_manual_prompt_edit_cannot_replace_a_newer_saved_prompt(
    app: object, publication: object, monkeypatch: object
) -> None:
    import json

    from flaskr.service.common import profile_onboarding as config

    old = json.dumps(
        {"revision": 1, "markdownflow": "?[...Answer]", "assistant_prompt": "Original"}
    )
    winner = json.dumps(
        {
            "revision": 2,
            "markdownflow": "?[...Answer]",
            "assistant_prompt": "Newer operator edit",
        }
    )
    publication.publish_profile_onboarding_database(
        app, expected_value=None, value=old, updated_by="first"
    )

    def read_then_race(_app: object) -> str:
        publication.publish_profile_onboarding_database(
            app, expected_value=old, value=winner, updated_by="second"
        )
        return old

    compiler = Mock()
    monkeypatch.setattr(config, "read_profile_onboarding_database", read_then_race)
    monkeypatch.setattr(config, "compile_profile_onboarding_assistant_prompt", compiler)
    payload = {
        "enabled": True,
        "markdownflow": "?[...Answer]",
        "assistant_prompt": "Stale operator edit",
    }
    with pytest.raises(AppError):
        config.update_profile_onboarding_config(
            app, payload=payload, operator_user_bid="first"
        )
    assert publication.read_profile_onboarding_database(app) == winner
    assert payload["assistant_prompt"] == "Stale operator edit"
    compiler.assert_not_called()


def test_rejected_enabled_prompt_clear_keeps_previously_saved_manual_prompt(
    app: object, publication: object, monkeypatch: object
) -> None:
    import json

    from flaskr.service.common import profile_onboarding as config

    old = json.dumps(
        {
            "revision": 1,
            "markdownflow": "?[...Answer]",
            "assistant_prompt": "Saved manual wording",
        }
    )
    publication.publish_profile_onboarding_database(
        app, expected_value=None, value=old, updated_by="operator"
    )
    compiler = Mock(side_effect=AssertionError("save must never compile the master"))
    monkeypatch.setattr(config, "compile_profile_onboarding_assistant_prompt", compiler)
    payload = {
        "enabled": True,
        "markdownflow": "?[...Answer]",
        "assistant_prompt": "",
        "config_revision": 1,
    }
    with pytest.raises(AppError, match="assistant_prompt"):
        config.update_profile_onboarding_config(
            app, payload=payload, operator_user_bid="operator"
        )
    assert publication.read_profile_onboarding_database(app) == old
    assert payload["assistant_prompt"] == ""
    compiler.assert_not_called()
