from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

import flaskr.dao as dao
from flaskr.common import config as config_module
from flaskr.service.billing.consts import BILLING_TRIAL_PRODUCT_BID
from flaskr.service.billing.models import BillingOrder, BillingProduct
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.models import UserInfo as UserEntity
from flaskr.service.user.repository import create_user_entity, upsert_credential
from tests.common.fixtures.bill_products import build_bill_products


def _get_models():
    from flaskr.service.shifu.models import DraftShifu, AiCourseAuth

    return DraftShifu, AiCourseAuth


def _seed_shifu(app, shifu_bid: str, owner_bid: str):
    with app.app_context():
        DraftShifu, AiCourseAuth = _get_models()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        AiCourseAuth.query.filter_by(course_id=shifu_bid).delete()

        draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="Test Shifu",
            description="desc",
            avatar_res_bid="res",
            keywords="test",
            llm="gpt",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=owner_bid,
            updated_user_bid=owner_bid,
        )
        dao.db.session.add(draft)
        dao.db.session.commit()


def _mock_user(monkeypatch, user_id: str, is_creator: bool = True):
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_creator=is_creator,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )
    return dummy_user


def _clear_config_caches() -> None:
    try:
        config_module.__ENHANCED_CONFIG__._cache.clear()
    except Exception:
        pass
    try:
        if config_module.__INSTANCE__ is not None:
            config_module.__INSTANCE__.enhanced._cache.clear()
    except Exception:
        pass


def _allow_email_login(monkeypatch) -> None:
    monkeypatch.setenv("LOGIN_METHODS_ENABLED", "phone,email")
    _clear_config_caches()


def _add_auth(app, shifu_bid: str, user_id: str, status: int):
    with app.app_context():
        _, AiCourseAuth = _get_models()
        dao.db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{user_id}",
                course_id=shifu_bid,
                user_id=user_id,
                auth_type=json.dumps(["view"]),
                status=status,
            )
        )
        dao.db.session.commit()


def _seed_user(app, *, user_bid: str, email: str):
    with app.app_context():
        entity = create_user_entity(
            user_bid=user_bid,
            identify=email,
            nickname=f"user-{user_bid}",
            language="en-US",
            state=USER_STATE_REGISTERED,
        )
        entity.is_creator = 0
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


def _ensure_trial_billing_enabled(monkeypatch):
    import flaskr.service.billing.auth_hooks  # noqa: F401

    monkeypatch.setattr(
        "flaskr.service.billing.trials._is_billing_enabled",
        lambda: True,
    )
    existing = BillingProduct.query.filter_by(
        product_bid=BILLING_TRIAL_PRODUCT_BID,
        deleted=0,
    ).first()
    if existing is None:
        dao.db.session.add_all(
            build_bill_products(product_bids=[BILLING_TRIAL_PRODUCT_BID])
        )
        dao.db.session.commit()


@pytest.mark.usefixtures("app")
class TestShifuPermissions:
    def test_list_permissions_only_active(self, monkeypatch, test_client, app):
        shifu_bid = "test-permission-list"
        owner_id = "owner-1"
        active_user = "user-active"
        inactive_user = "user-inactive"
        _seed_shifu(app, shifu_bid, owner_id)
        _add_auth(app, shifu_bid, active_user, status=1)
        _add_auth(app, shifu_bid, inactive_user, status=0)

        def fake_load_user_aggregate(user_id: str):
            return SimpleNamespace(
                user_bid=user_id,
                mobile="13800000000",
                email="",
                nickname=f"nick-{user_id}",
            )

        monkeypatch.setattr(
            "flaskr.service.shifu.route.load_user_aggregate",
            fake_load_user_aggregate,
            raising=False,
        )
        _mock_user(monkeypatch, owner_id)

        resp = test_client.get(
            f"/api/shifu/shifus/{shifu_bid}/permissions?contact_type=phone",
            headers={"Token": "test-token"},
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        items = payload["data"]["items"]
        assert len(items) == 1
        assert items[0]["user_id"] == active_user

    def test_remove_permissions_soft_delete(self, monkeypatch, test_client, app):
        shifu_bid = "test-permission-remove"
        owner_id = "owner-2"
        target_user = "user-target"
        _seed_shifu(app, shifu_bid, owner_id)
        _add_auth(app, shifu_bid, target_user, status=1)
        _mock_user(monkeypatch, owner_id)

        resp = test_client.post(
            f"/api/shifu/shifus/{shifu_bid}/permissions/remove",
            json={"user_id": target_user},
            headers={"Token": "test-token"},
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["removed"] is True

        with app.app_context():
            _, AiCourseAuth = _get_models()
            auth = AiCourseAuth.query.filter_by(
                course_id=shifu_bid, user_id=target_user
            ).first()
            assert auth is not None
            assert auth.status == 0

    def test_grant_view_permission_does_not_promote_creator(
        self, monkeypatch, test_client, app
    ):
        shifu_bid = "test-permission-grant-view"
        owner_id = "owner-grant-view"
        target_user = "user-grant-view"
        target_email = "viewer-grant@example.com"
        _seed_shifu(app, shifu_bid, owner_id)
        _seed_user(app, user_bid=target_user, email=target_email)
        _allow_email_login(monkeypatch)
        _mock_user(monkeypatch, owner_id)

        resp = test_client.post(
            f"/api/shifu/shifus/{shifu_bid}/permissions/grant",
            json={
                "contact_type": "email",
                "contacts": [target_email],
                "permission": "view",
            },
            headers={"Token": "test-token"},
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0

        with app.app_context():
            user = UserEntity.query.filter_by(user_bid=target_user).one()
            assert user.is_creator == 0
            assert BillingOrder.query.filter_by(creator_bid=target_user).count() == 0

    @pytest.mark.parametrize(
        ("permission", "expected_auth_types"),
        [
            ("edit", ["edit"]),
            ("publish", ["edit", "publish"]),
        ],
    )
    def test_grant_authoring_permission_promotes_creator_and_bootstraps_trial(
        self,
        monkeypatch,
        test_client,
        app,
        permission: str,
        expected_auth_types: list[str],
    ):
        shifu_bid = f"test-permission-grant-{permission}"
        owner_id = f"owner-grant-{permission}"
        target_user = f"user-grant-{permission}"
        target_email = f"{permission}-grant@example.com"
        _seed_shifu(app, shifu_bid, owner_id)
        _seed_user(app, user_bid=target_user, email=target_email)
        _allow_email_login(monkeypatch)

        with app.app_context():
            _ensure_trial_billing_enabled(monkeypatch)

        _mock_user(monkeypatch, owner_id)
        for _ in range(2):
            resp = test_client.post(
                f"/api/shifu/shifus/{shifu_bid}/permissions/grant",
                json={
                    "contact_type": "email",
                    "contacts": [target_email],
                    "permission": permission,
                },
                headers={"Token": "test-token"},
            )
            payload = resp.get_json(force=True)
            assert resp.status_code == 200
            assert payload["code"] == 0

        with app.app_context():
            _, AiCourseAuth = _get_models()
            user = UserEntity.query.filter_by(user_bid=target_user).one()
            auth = AiCourseAuth.query.filter_by(
                course_id=shifu_bid,
                user_id=target_user,
                status=1,
            ).one()
            trial_orders = BillingOrder.query.filter_by(
                creator_bid=target_user,
                product_bid=BILLING_TRIAL_PRODUCT_BID,
                deleted=0,
            ).all()

            assert user.is_creator == 1
            assert json.loads(auth.auth_type) == expected_auth_types
            assert len(trial_orders) == 1
