from decimal import Decimal
from types import SimpleNamespace

import pytest

import flaskr.dao as dao
from flaskr.service.common.models import ERROR_CODE
from flaskr.service.shifu.models import DraftOutlineItem, DraftShifu, LogDraftStruct


def _seed_shifu_with_outline(
    app, shifu_bid: str, outline_bid: str, user_id: str
) -> int:
    with app.app_context():
        DraftOutlineItem.query.filter_by(outline_item_bid=outline_bid).delete()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        LogDraftStruct.query.filter_by(shifu_bid=shifu_bid).delete()

        draft = DraftShifu(
            shifu_bid=shifu_bid,
            title="Draft Title",
            description="Draft description",
            avatar_res_bid="res",
            keywords="",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=user_id,
            updated_user_bid=user_id,
        )
        outline = DraftOutlineItem(
            outline_item_bid=outline_bid,
            shifu_bid=shifu_bid,
            title="Outline",
            parent_bid="",
            position="01",
            content="hello",
            created_user_bid=user_id,
            updated_user_bid=user_id,
        )
        dao.db.session.add_all([draft, outline])
        dao.db.session.commit()

        log = LogDraftStruct(
            struct_bid=f"struct-{shifu_bid}",
            shifu_bid=shifu_bid,
            struct="{}",
            created_user_bid=user_id,
            updated_user_bid=user_id,
        )
        dao.db.session.add(log)
        dao.db.session.commit()
        return int(log.id)


def _mock_user(monkeypatch, user_id: str):
    dummy_user = SimpleNamespace(
        user_id=user_id,
        is_creator=True,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


@pytest.mark.usefixtures("app")
class TestDraftConflict:
    def test_save_mdflow_conflict_returns_meta(self, monkeypatch, test_client, app):
        shifu_bid = "draft-conflict-1"
        outline_bid = "outline-conflict-1"
        user_id = "user-1"
        revision = _seed_shifu_with_outline(app, shifu_bid, outline_bid, user_id)

        _mock_user(monkeypatch, user_id)
        monkeypatch.setattr(
            "flaskr.service.shifu.route.shifu_permission_verification",
            lambda *_args, **_kwargs: True,
            raising=False,
        )

        resp = test_client.post(
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow",
            json={"data": "hello", "base_revision": revision + 1},
            headers={"Token": "test-token"},
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == ERROR_CODE["server.shifu.draftConflict"]
        assert payload["data"]["meta"]["revision"] == revision

    def test_save_mdflow_with_latest_revision(self, monkeypatch, test_client, app):
        shifu_bid = "draft-conflict-2"
        outline_bid = "outline-conflict-2"
        user_id = "user-2"
        revision = _seed_shifu_with_outline(app, shifu_bid, outline_bid, user_id)

        _mock_user(monkeypatch, user_id)
        monkeypatch.setattr(
            "flaskr.service.shifu.route.shifu_permission_verification",
            lambda *_args, **_kwargs: True,
            raising=False,
        )

        resp = test_client.post(
            f"/api/shifu/shifus/{shifu_bid}/outlines/{outline_bid}/mdflow",
            json={"data": "hello", "base_revision": revision},
            headers={"Token": "test-token"},
        )
        payload = resp.get_json(force=True)

        assert resp.status_code == 200
        assert payload["code"] == 0
        assert payload["data"]["new_revision"] == revision
