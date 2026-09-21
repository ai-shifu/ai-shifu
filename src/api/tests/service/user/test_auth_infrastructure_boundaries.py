"""Verify CAPTCHA cache failures, MySQL bootstrap locks, and worker entrypoints."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.user import captcha, password_utils, phone_flow, tasks

from tests.common.fixtures.fake_redis import FakeRedis


@pytest.mark.parametrize("raw", ["bad-json", "[]", "null"])
def test_corrupt_captcha_cache_is_deleted_and_cannot_authorize_a_ticket(
    app: object, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(captcha, "redis", cache)
    key = captcha._captcha_key(app, "challenge")
    cache.set(key, raw)
    with app.app_context(), pytest.raises(AppError) as error:
        captcha.verify_captcha_code(app, "challenge", "AAAA")
    assert error.value.code == ERROR_CODE["server.user.checkCodeExpired"]
    assert cache.get(key) is None


def test_captcha_attempt_cannot_extend_a_challenge_that_expired_during_verification(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = FakeRedis()
    monkeypatch.setattr(captcha, "redis", cache)
    captcha._store_captcha_payload(
        app,
        "challenge",
        {"digest": captcha._code_digest(app, "AAAA"), "attempts": 0},
        60,
    )
    monkeypatch.setattr(cache, "ttl", lambda _key: 0)
    with app.app_context(), pytest.raises(AppError) as error:
        captcha.verify_captcha_code(app, "challenge", "ZZZZ")
    assert error.value.code == ERROR_CODE["server.user.checkCodeExpired"]
    assert cache.get(captcha._captcha_key(app, "challenge")) is None


def test_captcha_key_defaults_keep_challenge_and_ticket_namespaces_separate(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "REDIS_KEY_PREFIX", "tests:")
    monkeypatch.setitem(app.config, "REDIS_KEY_PREFIX_CAPTCHA", "")
    monkeypatch.setitem(app.config, "REDIS_KEY_PREFIX_CAPTCHA_TICKET", "")
    assert captcha._captcha_key(app, "same") == "tests:captcha:same"
    assert captcha._ticket_key(app, "same") == "tests:captcha_ticket:same"


def test_captcha_generation_uses_random_characters_without_override(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(app.config, "CAPTCHA_CODE_OVERRIDE", "")
    monkeypatch.setattr(
        captcha, "_RANDOM", SimpleNamespace(choice=Mock(return_value="A"))
    )
    assert captcha._generate_code(app) == "AAAA"


def test_captcha_font_fallback_survives_missing_system_fonts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_font = object()
    monkeypatch.setattr(
        captcha.ImageFont, "truetype", Mock(side_effect=OSError("font unavailable"))
    )
    monkeypatch.setattr(
        captcha.ImageFont, "load_default", Mock(return_value=default_font)
    )
    assert captcha._load_captcha_font(34) is default_font


@pytest.mark.parametrize("acquired", [0, 1])
def test_mysql_bootstrap_lock_uses_named_lock_and_releases_it(
    app: object, monkeypatch: pytest.MonkeyPatch, acquired: int
) -> None:
    execute = Mock(return_value=SimpleNamespace(scalar=lambda: acquired))
    with app.app_context():
        monkeypatch.setattr(
            db.session,
            "get_bind",
            Mock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="mysql"))),
        )
        monkeypatch.setattr(db.session, "execute", execute)
        assert phone_flow._acquire_bootstrap_lock(app, timeout_seconds=2) is bool(
            acquired
        )
        assert "GET_LOCK" in str(execute.call_args.args[0])
        assert execute.call_args.args[1] == {
            "name": phone_flow.BOOTSTRAP_LOCK_NAME,
            "timeout_seconds": 2,
        }
        phone_flow._release_bootstrap_lock()
        assert "RELEASE_LOCK" in str(execute.call_args.args[0])
        assert execute.call_args.args[1] == {"name": phone_flow.BOOTSTRAP_LOCK_NAME}


def test_bootstrap_lock_failure_does_not_grant_account_roles(
    app: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(phone_flow, "_acquire_bootstrap_lock", Mock(return_value=False))
    with app.app_context():
        assert phone_flow.init_first_course(app, "account") is False


def test_migration_without_course_scope_does_not_move_learner_records(
    app: object,
) -> None:
    with app.app_context():
        assert (
            phone_flow.migrate_user_study_record(app, "source", "target", course_id=" ")
            is None
        )


def test_malformed_password_hash_fails_authentication() -> None:
    assert password_utils.verify_password("password", "not-a-bcrypt-hash") is False


def test_cancellation_worker_creates_non_http_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app as application

    worker_app = object()
    create = Mock(return_value=worker_app)
    monkeypatch.setattr(application, "create_app", create)
    assert tasks._create_task_app() is worker_app
    create.assert_called_once_with(serving_http=False)


def test_cancellation_task_normalizes_identifier_before_worker_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_app = object()
    execute = Mock(return_value={"status": "completed"})
    monkeypatch.setattr(tasks, "_create_task_app", Mock(return_value=worker_app))
    monkeypatch.setattr(tasks, "_execute_account_cancellation", execute)
    assert tasks.execute_account_cancellation_task.run(" cancellation ") == {
        "status": "completed"
    }
    assert execute.call_args.kwargs == {
        "cancellation_bid": "cancellation",
        "app": worker_app,
    }
