"""Verify WeChat subject selection is scoped by app and deterministic."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr import dao
from flaskr.dao import db
from flaskr.service.user.consts import (
    CREDENTIAL_STATE_UNVERIFIED,
    CREDENTIAL_STATE_VERIFIED,
    USER_STATE_REGISTERED,
)
from flaskr.service.user.models import AuthCredential
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity, load_user_aggregate

if TYPE_CHECKING:
    from collections.abc import Iterator

PLATFORM_APP = ""
CREATOR_APP = "wx-creator-app"


@pytest.fixture
def app() -> Iterator[Flask]:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def _create_learner() -> str:
    user_bid = uuid.uuid4().hex[:32]
    create_user_entity(
        user_bid=user_bid,
        identify="13800000000",
        nickname="Learner",
        language="zh-CN",
        avatar="",
        state=USER_STATE_REGISTERED,
    )
    db.session.flush()
    return user_bid


def _insert_open_id(
    user_bid: str,
    open_id: str,
    *,
    app_id: str = PLATFORM_APP,
    state: int = CREDENTIAL_STATE_VERIFIED,
) -> None:
    """Insert one open_id row the way ``upsert_wechat_credentials`` would."""
    identifier = f"{app_id}:{open_id}" if app_id else open_id
    db.session.add(
        AuthCredential(
            credential_bid=uuid.uuid4().hex[:32],
            user_bid=user_bid,
            provider_name="wechat",
            subject_id=open_id,
            subject_format="open_id",
            identifier=identifier,
            raw_profile='{"provider": "wechat", "metadata": {}}',
            state=state,
            deleted=0,
        )
    )
    db.session.flush()


def _cleanup(user_bid: str) -> None:
    AuthCredential.query.filter_by(user_bid=user_bid).delete()
    UserEntity.query.filter_by(user_bid=user_bid).delete()
    db.session.commit()


def test_returns_empty_without_any_wechat_credential(app: Flask) -> None:
    with app.app_context():
        user_bid = _create_learner()
        try:
            aggregate = load_user_aggregate(user_bid)
            assert aggregate.wechat_open_id == ""
            assert aggregate.wechat_open_id_for_app(CREATOR_APP) == ""
        finally:
            _cleanup(user_bid)


def test_each_app_gets_its_own_open_id(app: Flask) -> None:
    """A learner holds one open ID per WeChat app; charging must not mix them."""
    with app.app_context():
        user_bid = _create_learner()
        _insert_open_id(user_bid, "o_platform")
        _insert_open_id(user_bid, "o_creator", app_id=CREATOR_APP)
        try:
            aggregate = load_user_aggregate(user_bid)
            assert aggregate.wechat_open_id_for_app(PLATFORM_APP) == "o_platform"
            assert aggregate.wechat_open_id_for_app(CREATOR_APP) == "o_creator"
            assert aggregate.wechat_open_id == "o_platform"
        finally:
            _cleanup(user_bid)


def test_newest_binding_wins_within_one_app(app: Flask) -> None:
    """Signing in from another WeChat account adds a row; the new one is current."""
    with app.app_context():
        user_bid = _create_learner()
        _insert_open_id(user_bid, "o_previous")
        _insert_open_id(user_bid, "o_current")
        try:
            assert load_user_aggregate(user_bid).wechat_open_id == "o_current"
        finally:
            _cleanup(user_bid)


def test_verified_beats_a_newer_unverified_binding(app: Flask) -> None:
    with app.app_context():
        user_bid = _create_learner()
        _insert_open_id(user_bid, "o_verified")
        _insert_open_id(user_bid, "o_unverified", state=CREDENTIAL_STATE_UNVERIFIED)
        try:
            assert load_user_aggregate(user_bid).wechat_open_id == "o_verified"
        finally:
            _cleanup(user_bid)


def test_falls_back_across_apps_rather_than_returning_nothing(app: Flask) -> None:
    """A creator may run their own OAuth app while charging through the platform."""
    with app.app_context():
        user_bid = _create_learner()
        _insert_open_id(user_bid, "o_creator", app_id=CREATOR_APP)
        try:
            aggregate = load_user_aggregate(user_bid)
            assert aggregate.wechat_open_id_for_app(PLATFORM_APP) == "o_creator"
            assert aggregate.wechat_open_id == "o_creator"
        finally:
            _cleanup(user_bid)
