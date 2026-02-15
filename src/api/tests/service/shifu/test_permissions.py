from decimal import Decimal
import json
from types import SimpleNamespace

import pytest

import flaskr.dao as dao


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
