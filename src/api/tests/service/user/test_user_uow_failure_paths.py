"""Unit-of-work behavior for the B3 user call sites.

Covers the verification-code two-step (record durable before delivery),
onboarding scene completion racing a concurrent insert, the password flows
moved out of the route, and the guest-token cache that must only be
populated after the guest account commits.
"""

from __future__ import annotations

import uuid

import pytest
from flaskr import dao
from flaskr.service.common.models import AppError
from flaskr.service.user import onboarding, password_flow
from flaskr.service.user import utils as user_utils
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import (
    AuthCredential,
    UserOnboardingState,
    UserVerifyCode,
)
from flaskr.service.user.password_utils import verify_password
from flaskr.service.user.repository import (
    create_user_entity,
    get_password_hash,
    upsert_credential,
)


def _committed_rows(app: object, table: object, *conditions: object) -> list[object]:
    with app.app_context(), dao.db.engine.connect() as connection:
        return connection.execute(table.select().where(*conditions)).fetchall()


def _seed_user(app: object, user_bid: str, email: str) -> None:
    create_user_entity(
        user_bid=user_bid,
        identify=email,
        nickname=f"user-{user_bid[:6]}",
        language="en-US",
        state=USER_STATE_REGISTERED,
    )
    dao.db.session.flush()
    upsert_credential(
        app,
        user_bid=user_bid,
        provider_name="email",
        subject_id=email,
        subject_format="email",
        identifier=email,
        metadata={},
        verified=True,
    )
    dao.db.session.commit()


def test_verification_record_is_durable_before_delivery_and_marked_after(
    app: object, monkeypatch: object
) -> None:
    identifier = f"{uuid.uuid4().hex[:8]}@example.com"
    seen: list[tuple[int, int]] = []

    def deliver(_challenge: object) -> bool:
        rows = _committed_rows(
            app, UserVerifyCode.__table__, UserVerifyCode.mail == identifier
        )
        seen.append((len(rows), rows[0].verify_code_send if rows else -1))
        return True

    monkeypatch.setattr(user_utils, "_enforce_verification_ip_limit", lambda *_a: None)
    with app.app_context():
        challenge = user_utils._prepare_verification_challenge(
            app, identifier, None, user_utils._EMAIL_CHALLENGE_POLICY, deliver
        )
        assert challenge.record.verify_code_send == 1

    # Delivery observed the committed record (not yet marked as sent) ...
    assert seen == [(1, 0)]
    # ... and the second step marked it as sent.
    rows = _committed_rows(
        app, UserVerifyCode.__table__, UserVerifyCode.mail == identifier
    )
    assert [row.verify_code_send for row in rows] == [1]


def test_verification_record_survives_a_failed_delivery(
    app: object, monkeypatch: object
) -> None:
    identifier = f"{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(user_utils, "_enforce_verification_ip_limit", lambda *_a: None)

    with app.app_context(), pytest.raises(AppError):
        user_utils._prepare_verification_challenge(
            app,
            identifier,
            None,
            user_utils._EMAIL_CHALLENGE_POLICY,
            lambda _challenge: False,
        )

    rows = _committed_rows(
        app, UserVerifyCode.__table__, UserVerifyCode.mail == identifier
    )
    assert [row.verify_code_send for row in rows] == [0]


def test_onboarding_completion_reapplies_after_losing_the_insert_race(
    app: object, monkeypatch: object
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    monkeypatch.setattr(onboarding, "_load_user_entity", lambda _bid: object())
    monkeypatch.setattr(
        onboarding,
        "_resolve_user_segment",
        lambda _user: onboarding.USER_SEGMENT_NEW_CREATOR,
    )
    original_add = dao.db.session.add
    state = {"raced": False}

    def racing_add(instance: object) -> None:
        # First insert attempt: a concurrent request "wins" by inserting the
        # row through another connection, then our commit hits the unique key.
        if isinstance(instance, UserOnboardingState) and not state["raced"]:
            state["raced"] = True
            with dao.db.engine.begin() as connection:
                connection.execute(
                    UserOnboardingState.__table__.insert().values(
                        user_bid=user_bid,
                        scene_key=instance.scene_key,
                        version=instance.version,
                        status="skipped",
                        trigger_source="settings",
                        completed_at=None,
                    )
                )
        original_add(instance)

    with app.app_context():
        monkeypatch.setattr(dao.db.session, "add", racing_add)
        scene_key = next(iter(onboarding.SUPPORTED_SCENES))
        trigger_source = next(iter(onboarding.SUPPORTED_TRIGGER_SOURCES))
        result = onboarding.complete_onboarding_scene(
            app,
            user_bid,
            scene_key=scene_key,
            version=onboarding.ONBOARDING_VERSION,
            trigger_source=trigger_source,
        )
        monkeypatch.undo()

    assert state["raced"] is True
    assert result["completed"] is True
    rows = _committed_rows(
        app, UserOnboardingState.__table__, UserOnboardingState.user_bid == user_bid
    )
    assert [(row.status, row.trigger_source) for row in rows] == [
        (onboarding.STATUS_COMPLETED, trigger_source)
    ]


def test_set_password_late_failure_persists_no_credential(
    app: object, monkeypatch: object
) -> None:
    user_bid = uuid.uuid4().hex[:32]
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(
        password_flow, "consume_verification_code", lambda *_a, **_k: None
    )

    def failing_hash(*_args: object, **_kwargs: object) -> str:
        message = "hash boom"
        raise RuntimeError(message)

    monkeypatch.setattr(password_flow, "set_password_hash", failing_hash)

    with app.app_context():
        _seed_user(app, user_bid, email)
        with pytest.raises(RuntimeError, match="hash boom"):
            password_flow.set_password(
                app,
                user_bid=user_bid,
                identifier=email,
                code="9999",
                new_password="Passw0rd!x",
            )

    rows = _committed_rows(
        app,
        AuthCredential.__table__,
        AuthCredential.user_bid == user_bid,
        AuthCredential.provider_name == "password",
    )
    assert rows == []


def test_password_set_change_reset_round_trip(app: object, monkeypatch: object) -> None:
    user_bid = uuid.uuid4().hex[:32]
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(
        password_flow, "consume_verification_code", lambda *_a, **_k: None
    )

    with app.app_context():
        _seed_user(app, user_bid, email)
        password_flow.set_password(
            app,
            user_bid=user_bid,
            identifier=None,
            code="9999",
            new_password="Passw0rd!1",
        )
        password_flow.change_password(
            app, user_bid=user_bid, old_password="Passw0rd!1", new_password="Passw0rd!2"
        )
        password_flow.reset_password(
            app, identifier=email, code="9999", new_password="Passw0rd!3"
        )
        dao.db.session.expire_all()
        cred = AuthCredential.query.filter_by(
            user_bid=user_bid, provider_name="password", deleted=0
        ).one()
        assert verify_password("Passw0rd!3", get_password_hash(cred))

    rows = _committed_rows(
        app,
        AuthCredential.__table__,
        AuthCredential.user_bid == user_bid,
        AuthCredential.provider_name == "password",
    )
    assert len(rows) == 1


def test_transaction_owning_flows_reject_nested_callers(app: object) -> None:
    """Challenge issuance and onboarding completion own their transactions."""
    from flaskr.dao.uow import unit_of_work

    def nested_challenge() -> None:
        with unit_of_work():
            user_utils._prepare_verification_challenge(
                app, "13800000000", None, None, lambda _c: True
            )

    def nested_onboarding() -> None:
        with unit_of_work():
            onboarding.complete_onboarding_scene(
                app,
                user_bid="uow-user",
                scene_key="learner_profile",
                version="v1",
                trigger_source="manual",
            )

    with app.app_context():
        with pytest.raises(RuntimeError, match="must not be called inside"):
            nested_challenge()
        with pytest.raises(RuntimeError, match="must not be called inside"):
            nested_onboarding()


def test_avatar_previous_object_is_deleted_only_after_commit(
    app: object, monkeypatch: object
) -> None:
    from types import SimpleNamespace

    from flaskr.service.user import user as user_module

    user_bid = uuid.uuid4().hex[:32]
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    deleted: list[str] = []
    monkeypatch.setattr(
        user_module,
        "_try_delete_local_file_by_url",
        lambda _app, url: deleted.append(url),
    )
    monkeypatch.setattr(user_module, "is_oss_profile_configured", lambda _p: False)
    monkeypatch.setattr(
        user_module,
        "upload_to_storage",
        lambda *_a, **_k: SimpleNamespace(
            url="/static/avatar/new.png", provider="local"
        ),
    )
    avatar = SimpleNamespace(filename="new.png")

    with app.app_context():
        _seed_user(app, user_bid, email)
        entity = user_module.get_user_entity_by_bid(user_bid, include_deleted=True)
        entity.avatar = "/static/avatar/old.png"
        dao.db.session.commit()

        def failing_update(*_a: object, **_k: object) -> None:
            message = "update boom"
            raise RuntimeError(message)

        monkeypatch.setattr(user_module, "update_user_entity_fields", failing_update)
        with pytest.raises(RuntimeError, match="update boom"):
            user_module.upload_user_avatar(app, user_bid, avatar)
        # The rollback keeps the old avatar reachable, and the object uploaded
        # by the failed attempt is removed instead of being orphaned.
        assert deleted == ["/static/avatar/new.png"]
        deleted.clear()

        monkeypatch.undo()
        monkeypatch.setattr(
            user_module,
            "_try_delete_local_file_by_url",
            lambda _app, url: deleted.append(url),
        )
        monkeypatch.setattr(user_module, "is_oss_profile_configured", lambda _p: False)
        monkeypatch.setattr(
            user_module,
            "upload_to_storage",
            lambda *_a, **_k: SimpleNamespace(
                url="/static/avatar/new.png", provider="local"
            ),
        )
        assert user_module.upload_user_avatar(app, user_bid, avatar) == (
            "/static/avatar/new.png"
        )
        assert deleted == ["/static/avatar/old.png"]


def test_avatar_upload_removes_the_orphan_when_the_transaction_rolls_back(
    app: object, monkeypatch: object
) -> None:
    """A failed avatar update must not leave the uploaded object behind."""
    from types import SimpleNamespace

    from flaskr.service.common.storage import STORAGE_PROVIDER_OSS
    from flaskr.service.user import user as user_module

    user_bid = uuid.uuid4().hex[:32]
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    deleted_objects: list[str] = []

    class _Bucket:
        def object_exists(self, key: str) -> bool:
            return key == "new-object-key"

        def delete_object(self, key: str) -> None:
            deleted_objects.append(key)

    monkeypatch.setattr(user_module, "_try_delete_local_file_by_url", lambda *_a: None)
    monkeypatch.setattr(user_module, "is_oss_profile_configured", lambda _p: True)
    monkeypatch.setattr(user_module, "get_oss_config", lambda _p: object())
    monkeypatch.setattr(user_module, "create_oss_bucket", lambda _c: _Bucket())
    monkeypatch.setattr(
        user_module,
        "upload_to_storage",
        lambda *_a, **_k: SimpleNamespace(
            url="https://cdn.example/new.png",
            provider=STORAGE_PROVIDER_OSS,
            object_key="new-object-key",
            bucket="avatars",
        ),
    )

    def failing_update(*_a: object, **_k: object) -> None:
        message = "update boom"
        raise RuntimeError(message)

    monkeypatch.setattr(user_module, "update_user_entity_fields", failing_update)

    with app.app_context():
        _seed_user(app, user_bid, email)
        dao.db.session.commit()
        with pytest.raises(RuntimeError, match="update boom"):
            user_module.upload_user_avatar(
                app, user_bid, SimpleNamespace(filename="new.png")
            )

    assert deleted_objects == ["new-object-key"]
