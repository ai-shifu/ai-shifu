from __future__ import annotations

from flask import Flask
import pytest

import flaskr.dao as dao
from flaskr.service.billing.ownership import (
    resolve_shifu_creator_bid,
    resolve_usage_creator_bid,
)
from flaskr.service.metering.consts import (
    BILL_USAGE_SCENE_DEBUG,
    BILL_USAGE_SCENE_PREVIEW,
    BILL_USAGE_SCENE_PROD,
)
from flaskr.service.metering.models import BillUsageRecord
from flaskr.service.shifu.models import DraftShifu, PublishedShifu


@pytest.fixture
def billing_ownership_app():
    app = Flask(__name__)
    app.testing = True
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={
            "ai_shifu_saas": "sqlite:///:memory:",
            "ai_shifu_admin": "sqlite:///:memory:",
        },
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TZ="UTC",
    )
    dao.db.init_app(app)
    with app.app_context():
        dao.db.create_all()
        yield app
        dao.db.session.remove()
        dao.db.drop_all()


def test_resolve_shifu_creator_bid_prefers_draft_record(
    billing_ownership_app: Flask,
) -> None:
    with billing_ownership_app.app_context():
        dao.db.session.add(
            DraftShifu(
                shifu_bid="shifu-1",
                created_user_bid="creator-draft-1",
            )
        )
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-1",
                created_user_bid="creator-published-1",
            )
        )
        dao.db.session.commit()

    assert (
        resolve_shifu_creator_bid(billing_ownership_app, "shifu-1") == "creator-draft-1"
    )


def test_resolve_usage_creator_bid_accepts_usage_record(
    billing_ownership_app: Flask,
) -> None:
    with billing_ownership_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-usage-1",
                created_user_bid="creator-usage-1",
            )
        )
        usage = BillUsageRecord(
            usage_bid="usage-1",
            shifu_bid="shifu-usage-1",
        )
        dao.db.session.add(usage)
        dao.db.session.commit()

    with billing_ownership_app.app_context():
        persisted_usage = BillUsageRecord.query.filter_by(usage_bid="usage-1").one()

    assert (
        resolve_usage_creator_bid(billing_ownership_app, persisted_usage)
        == "creator-usage-1"
    )


def test_resolve_usage_creator_bid_accepts_usage_payload_dict(
    billing_ownership_app: Flask,
) -> None:
    with billing_ownership_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-payload-1",
                created_user_bid="creator-payload-1",
            )
        )
        dao.db.session.commit()

    assert (
        resolve_usage_creator_bid(
            billing_ownership_app,
            {"usage_bid": "usage-payload-1", "shifu_bid": "shifu-payload-1"},
        )
        == "creator-payload-1"
    )


@pytest.mark.parametrize(
    ("usage_scene", "usage_bid"),
    [
        (BILL_USAGE_SCENE_PROD, "usage-prod-1"),
        (BILL_USAGE_SCENE_PREVIEW, "usage-preview-1"),
        (BILL_USAGE_SCENE_DEBUG, "usage-debug-1"),
    ],
)
def test_resolve_usage_creator_bid_uses_same_creator_for_all_billing_scenes(
    billing_ownership_app: Flask,
    usage_scene: int,
    usage_bid: str,
) -> None:
    with billing_ownership_app.app_context():
        dao.db.session.add(
            PublishedShifu(
                shifu_bid="shifu-scene-1",
                created_user_bid="creator-scene-1",
            )
        )
        dao.db.session.commit()

    assert (
        resolve_usage_creator_bid(
            billing_ownership_app,
            {
                "usage_bid": usage_bid,
                "shifu_bid": "shifu-scene-1",
                "usage_scene": usage_scene,
            },
        )
        == "creator-scene-1"
    )


def test_resolve_usage_creator_bid_returns_none_without_match(
    billing_ownership_app: Flask,
) -> None:
    assert resolve_shifu_creator_bid(billing_ownership_app, "") is None
    assert (
        resolve_usage_creator_bid(
            billing_ownership_app,
            {"usage_bid": "usage-missing-1", "shifu_bid": "missing-shifu-1"},
        )
        is None
    )


def test_resolve_usage_creator_bid_falls_back_to_debug_creator_user_bid(
    billing_ownership_app: Flask,
) -> None:
    assert (
        resolve_usage_creator_bid(
            billing_ownership_app,
            {
                "usage_bid": "usage-debug-direct-1",
                "user_bid": "creator-debug-direct-1",
                "shifu_bid": "",
                "usage_scene": BILL_USAGE_SCENE_DEBUG,
            },
        )
        == "creator-debug-direct-1"
    )
