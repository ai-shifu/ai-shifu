from decimal import Decimal
from types import SimpleNamespace

import flaskr.dao as dao
from flaskr.service.common.models import ERROR_CODE


def _get_models():
    from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu

    return DraftShifu, DraftOutlineItem


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


def _seed_shifu_with_outline(
    app,
    shifu_bid: str,
    outline_bid: str,
    owner_bid: str,
    content: str,
) -> int:
    with app.app_context():
        DraftShifu, DraftOutlineItem = _get_models()
        DraftOutlineItem.query.filter_by(
            shifu_bid=shifu_bid, outline_item_bid=outline_bid
        ).delete()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()

        draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="History Route Test",
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
        dao.db.session.flush()

        outline = DraftOutlineItem(
            shifu_bid=shifu_bid,
            outline_item_bid=outline_bid,
            title="Unit A",
            content=content,
            updated_user_bid=owner_bid,
            created_user_bid=owner_bid,
        )
        dao.db.session.add(outline)
        dao.db.session.commit()
        return int(outline.id)


def test_get_mdflow_history_version_detail_route_success(monkeypatch, test_client, app):
    shifu_bid = "test-route-history-detail-1"
    outline_bid = "test-route-outline-1"
    owner_bid = "test-route-owner-1"
    content = "History detail route content"
    version_id = _seed_shifu_with_outline(
        app,
        shifu_bid,
        outline_bid,
        owner_bid,
        content,
    )
    _mock_user(monkeypatch, owner_bid)

    resp = test_client.get(
        f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history/{version_id}?timezone=UTC",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    data = payload["data"]
    assert data["version_id"] == version_id
    assert data["content"] == content
    assert data["updated_user_bid"] == owner_bid
    assert data["updated_user_name"] == owner_bid


def test_get_mdflow_history_version_detail_route_rejects_invalid_version_id(
    monkeypatch, test_client, app
):
    shifu_bid = "test-route-history-detail-2"
    outline_bid = "test-route-outline-2"
    owner_bid = "test-route-owner-2"
    _seed_shifu_with_outline(
        app,
        shifu_bid,
        outline_bid,
        owner_bid,
        "route invalid version id",
    )
    _mock_user(monkeypatch, owner_bid)

    resp = test_client.get(
        f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history/abc",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == ERROR_CODE["server.common.paramsError"]


def test_restore_mdflow_history_route_returns_deleted_flag(
    monkeypatch, test_client, app
):
    shifu_bid = "test-route-history-restore-1"
    outline_bid = "test-route-outline-restore-1"
    owner_bid = "test-route-owner-restore-1"
    _seed_shifu_with_outline(
        app,
        shifu_bid,
        outline_bid,
        owner_bid,
        "restore route baseline",
    )
    _mock_user(monkeypatch, owner_bid)

    with app.app_context():
        _, DraftOutlineItem = _get_models()
        latest = (
            DraftOutlineItem.query.filter_by(
                shifu_bid=shifu_bid,
                outline_item_bid=outline_bid,
            )
            .order_by(DraftOutlineItem.id.desc())
            .first()
        )
        assert latest is not None

        target_version = latest.clone()
        target_version.content = "restore route changed"
        target_version.updated_user_bid = owner_bid
        dao.db.session.add(target_version)
        dao.db.session.flush()
        target_version_id = int(target_version.id)

        deleted_snapshot = target_version.clone()
        deleted_snapshot.deleted = 1
        deleted_snapshot.updated_user_bid = owner_bid
        dao.db.session.add(deleted_snapshot)
        dao.db.session.commit()

    resp = test_client.post(
        f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow/history/restore",
        headers={"Token": "test-token"},
        json={"version_id": target_version_id, "base_revision": target_version_id},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["lesson_deleted"] is True
    assert payload["data"]["restored"] is False
