from decimal import Decimal
from types import SimpleNamespace
import json

import flaskr.dao as dao


def _seed_shifu(app, shifu_bid: str, owner_bid: str) -> None:
    from flaskr.service.shifu.models import DraftShifu, AiCourseAuth

    with app.app_context():
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        AiCourseAuth.query.filter_by(course_id=shifu_bid).delete()

        dao.db.session.add(
            DraftShifu(
                shifu_bid=shifu_bid,
                title="Import Activation Course",
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
        )
        dao.db.session.commit()


def _add_shared_permission(app, shifu_bid: str, user_id: str) -> None:
    from flaskr.service.shifu.models import AiCourseAuth

    with app.app_context():
        dao.db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{shifu_bid}-{user_id}",
                course_id=shifu_bid,
                user_id=user_id,
                auth_type=json.dumps(["edit"]),
                status=1,
            )
        )
        dao.db.session.commit()


def _mock_user(monkeypatch, user_id: str, *, is_creator: bool = True):
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


def test_admin_import_activation_rejects_shared_permission_user(
    monkeypatch, test_client, app
):
    shifu_bid = "import-permission-course-1"
    owner_bid = "owner-import-1"
    shared_bid = "shared-import-1"
    _seed_shifu(app, shifu_bid, owner_bid)
    _add_shared_permission(app, shifu_bid, shared_bid)
    _mock_user(monkeypatch, shared_bid, is_creator=True)

    response = test_client.post(
        "/api/order/admin/orders/import-activation",
        json={
            "mobile": "13800138000",
            "course_id": shifu_bid,
            "contact_type": "phone",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401


def test_admin_import_activation_allows_owner(monkeypatch, test_client, app):
    shifu_bid = "import-permission-course-2"
    owner_bid = "owner-import-2"
    _seed_shifu(app, shifu_bid, owner_bid)
    _mock_user(monkeypatch, owner_bid, is_creator=True)

    monkeypatch.setattr(
        "flaskr.route.order.get_shifu_info",
        lambda _app, _shifu_bid, _preview: SimpleNamespace(price=Decimal("0")),
        raising=False,
    )
    monkeypatch.setattr(
        "flaskr.route.order.import_activation_orders",
        lambda _app, _mobiles, _course_id, _user_nick_name, contact_type="phone": {
            "success": [{"mobile": "13800138000", "order_bid": "order-1"}],
            "failed": [],
            "contact_type": contact_type,
        },
        raising=False,
    )

    response = test_client.post(
        "/api/order/admin/orders/import-activation",
        json={
            "mobile": "13800138000",
            "course_id": shifu_bid,
            "contact_type": "phone",
        },
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["success"][0]["order_bid"] == "order-1"
