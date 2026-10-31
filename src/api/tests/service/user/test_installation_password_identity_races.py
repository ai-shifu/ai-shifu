"""Keep first setup and ordinary contact creation on one account identity."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.user import email_flow, installation, local_accounts, phone_flow
from flaskr.service.user.auth.base import OAuthCallbackRequest
from flaskr.service.user.auth.providers import google
from flaskr.service.user.auth.providers.google import GoogleAuthProvider, _encode_state
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.installation_models import InstallationState, LocalAdminAccount
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity
from sqlalchemy import event

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def identity_race_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Flask]:
    from flaskr.service.user import post_auth, utils

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'identity-race.db'}",
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"timeout": 10, "check_same_thread": False}
        },
        SECRET_KEY="synthetic-identity-race-secret",
        TOKEN_EXPIRE_TIME=3600,
    )
    db.init_app(app)
    monkeypatch.setattr(phone_flow, "consume_verification_code", Mock())
    monkeypatch.setattr(email_flow, "consume_verification_code", Mock())
    monkeypatch.setattr(utils, "ensure_demo_course_permissions", Mock())
    monkeypatch.setattr(post_auth, "run_post_auth_extensions", Mock())
    monkeypatch.setattr(
        google,
        "_resolve_redirect_uri",
        lambda *_args: "http://localhost/login/google-callback",
    )
    with app.app_context():
        db.create_all(bind_key=None)
        db.session.add(InstallationState(id=1, mode="managed"))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all(bind_key=None)


def _ordinary_login(app: Flask, kind: str, identifier: str) -> object:
    with app.app_context():
        if kind == "google":
            profile = {
                "sub": "synthetic-google-subject",
                "email": identifier,
                "email_verified": True,
            }
            response = Mock()
            response.json.return_value = profile
            session = Mock()
            session.get.return_value = response
            provider = GoogleAuthProvider()
            provider._create_session = Mock(return_value=session)
            state = _encode_state(
                app, {"redirect_uri": "http://localhost/login/google-callback"}
            )
            with app.test_request_context("/login/google-callback"):
                return provider.handle_oauth_callback(
                    app, OAuthCallbackRequest(code="synthetic-google-code", state=state)
                ).token
        if kind == "phone":
            token, _created, _context = phone_flow.verify_phone_code(
                app, user_id=None, phone=identifier, code="synthetic-code"
            )
        else:
            token, _created, _context = email_flow.verify_email_code(
                app, user_id=None, email=identifier, code="synthetic-code"
            )
        return token


@pytest.mark.parametrize("kind", ["phone", "email", "google"])
def test_setup_winning_contact_creation_is_reused_by_waiting_ordinary_login(
    identity_race_app: Flask, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = identity_race_app
    identifier = "13800138000" if kind == "phone" else "owner@example.com"
    token = installation.issue_setup_token(app)
    setup_locked = threading.Event()
    finish_setup = threading.Event()
    ordinary_waiting = threading.Event()
    ordinary_thread: set[int] = set()
    original_write = local_accounts.write_password_credential

    def paused_write(*args: object, **kwargs: object) -> object:
        setup_locked.set()
        assert finish_setup.wait(timeout=5)
        return original_write(*args, **kwargs)

    def login() -> object:
        ordinary_thread.add(threading.get_ident())
        return _ordinary_login(app, kind, identifier)

    def observe_wait(
        _conn: object, _cursor: object, statement: str, *_args: object
    ) -> None:
        if (
            threading.get_ident() in ordinary_thread
            and statement.lstrip().upper().startswith("UPDATE USER_INSTALLATION_STATE")
        ):
            ordinary_waiting.set()

    monkeypatch.setattr(local_accounts, "write_password_credential", paused_write)
    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", observe_wait)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            setup = executor.submit(
                installation.initialize_admin,
                app,
                setup_token=token,
                identifier=identifier,
                password="Initial123",
                request_origin="http://localhost:8080",
            )
            try:
                assert setup_locked.wait(timeout=5)
                ordinary = executor.submit(login)
                assert ordinary_waiting.wait(timeout=5)
                with pytest.raises(TimeoutError):
                    ordinary.result(timeout=0.2)
            finally:
                finish_setup.set()
            user_bid = setup.result(timeout=5)
            assert ordinary.result(timeout=5).userInfo.user_id == user_bid
    finally:
        event.remove(engine, "before_cursor_execute", observe_wait)
    with app.app_context():
        assert UserEntity.query.filter_by(user_identify=identifier).count() == 1
        assert (
            AuthCredential.query.filter_by(provider_name=kind, identifier=identifier)
            .one()
            .user_bid
            == user_bid
        )
        assert LocalAdminAccount.query.one().user_bid == user_bid


@pytest.mark.parametrize("kind", ["phone", "email", "google"])
def test_ordinary_contact_winning_creation_cannot_be_promoted_or_overwritten(
    identity_race_app: Flask, kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = identity_race_app
    identifier = "13800138000" if kind == "phone" else "owner@example.com"
    token = installation.issue_setup_token(app)
    ordinary_locked = threading.Event()
    finish_login = threading.Event()
    setup_waiting = threading.Event()
    setup_thread: set[int] = set()
    flow = phone_flow if kind == "phone" else google if kind == "google" else email_flow
    original_ensure = flow.ensure_user_for_identifier

    def paused_ensure(*args: object, **kwargs: object) -> object:
        ordinary_locked.set()
        assert finish_login.wait(timeout=5)
        return original_ensure(*args, **kwargs)

    def setup() -> str:
        setup_thread.add(threading.get_ident())
        return installation.initialize_admin(
            app,
            setup_token=token,
            identifier=identifier,
            password="Initial123",
            request_origin="http://localhost:8080",
        )

    def observe_wait(
        _conn: object, _cursor: object, statement: str, *_args: object
    ) -> None:
        if (
            threading.get_ident() in setup_thread
            and statement.lstrip().upper().startswith("UPDATE USER_INSTALLATION_STATE")
        ):
            setup_waiting.set()

    monkeypatch.setattr(flow, "ensure_user_for_identifier", paused_ensure)
    with app.app_context():
        engine = db.engine
    event.listen(engine, "before_cursor_execute", observe_wait)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            ordinary = executor.submit(_ordinary_login, app, kind, identifier)
            try:
                assert ordinary_locked.wait(timeout=5)
                initialize = executor.submit(setup)
                assert setup_waiting.wait(timeout=5)
                with pytest.raises(TimeoutError):
                    initialize.result(timeout=0.2)
            finally:
                finish_login.set()
            user_bid = ordinary.result(timeout=5).userInfo.user_id
            with pytest.raises(AppError):
                initialize.result(timeout=5)
    finally:
        event.remove(engine, "before_cursor_execute", observe_wait)
    with app.app_context():
        user = UserEntity.query.filter_by(user_identify=identifier).one()
        assert user.user_bid == user_bid
        assert not user.is_operator
        assert LocalAdminAccount.query.count() == 0
        assert AuthCredential.query.filter_by(provider_name="password").count() == 0
        state = db.session.get(InstallationState, 1)
        assert state.initialized_at is None
        assert state.token_digest


def test_identity_barrier_joins_rollback_and_completed_installations_do_not_write_lock(
    identity_race_app: Flask,
) -> None:
    app = identity_race_app

    def create_then_fail() -> None:
        with unit_of_work():
            assert installation.guard_pending_installation_identity_creation()
            create_user_entity(
                user_bid="rolled-back-contact",
                identify="rollback@example.com",
                state=USER_STATE_REGISTERED,
            )
            message = "rollback"
            raise RuntimeError(message)

    with app.app_context():
        with pytest.raises(RuntimeError, match="rollback"):
            create_then_fail()
        assert (
            UserEntity.query.filter_by(user_bid="rolled-back-contact").first() is None
        )
    token = installation.issue_setup_token(app)
    installation.initialize_admin(
        app,
        setup_token=token,
        identifier="owner@example.com",
        password="Initial123",
        request_origin="http://localhost:8080",
    )
    statements: list[str] = []
    with app.app_context():
        engine = db.engine

        def record(
            _conn: object, _cursor: object, statement: str, *_args: object
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            with unit_of_work():
                assert not installation.guard_pending_installation_identity_creation()
        finally:
            event.remove(engine, "before_cursor_execute", record)
    assert not any(
        statement.lstrip().upper().startswith("UPDATE") for statement in statements
    )
