from decimal import Decimal
import json
from types import SimpleNamespace

import flaskr.dao as dao


def _seed_course(app, shifu_bid: str, owner_bid: str) -> None:
    from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedShifu

    with app.app_context():
        AiCourseAuth.query.filter_by(course_id=shifu_bid).delete()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        PublishedShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        for model in (DraftShifu, PublishedShifu):
            dao.db.session.add(
                model(
                    shifu_bid=shifu_bid,
                    title="Preview Course",
                    description="Preview course description",
                    avatar_res_bid="",
                    keywords="preview",
                    llm="gpt-test",
                    llm_temperature=Decimal("0"),
                    llm_system_prompt="",
                    price=Decimal("0"),
                    created_user_bid=owner_bid,
                    updated_user_bid=owner_bid,
                )
            )
        dao.db.session.commit()


def _add_course_auth(
    app,
    *,
    shifu_bid: str,
    user_bid: str,
    auth_type: list[str],
    status: int = 1,
) -> None:
    from flaskr.service.shifu.models import AiCourseAuth

    with app.app_context():
        dao.db.session.add(
            AiCourseAuth(
                course_auth_id=f"auth-{shifu_bid}-{user_bid}",
                course_id=shifu_bid,
                user_id=user_bid,
                auth_type=json.dumps(auth_type),
                status=status,
            )
        )
        dao.db.session.commit()


def _mock_user(monkeypatch, user_bid: str, *, is_creator: bool = False) -> None:
    dummy_user = SimpleNamespace(
        user_id=user_bid,
        is_creator=is_creator,
        is_operator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: dummy_user,
        raising=False,
    )


def _assert_no_permission(response) -> None:
    payload = response.get_json(force=True)
    assert response.status_code == 200
    assert payload["code"] == 401
    assert payload["message"] == "No permission"


def test_preview_course_info_allows_creator(monkeypatch, test_client, app):
    shifu_bid = "preview-permission-owner"
    owner_bid = "owner-preview-info"
    _seed_course(app, shifu_bid, owner_bid)
    _mock_user(monkeypatch, owner_bid, is_creator=True)

    resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["bid"] == shifu_bid


def test_preview_course_info_allows_active_view_collaborator(
    monkeypatch, test_client, app
):
    shifu_bid = "preview-permission-collaborator"
    owner_bid = "owner-preview-collab"
    collaborator_bid = "user-preview-collab"
    _seed_course(app, shifu_bid, owner_bid)
    _add_course_auth(
        app,
        shifu_bid=shifu_bid,
        user_bid=collaborator_bid,
        auth_type=["view"],
    )
    _mock_user(monkeypatch, collaborator_bid)

    resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["bid"] == shifu_bid


def test_preview_course_info_rejects_user_without_course_permission(
    monkeypatch, test_client, app
):
    shifu_bid = "preview-permission-denied"
    _seed_course(app, shifu_bid, "owner-preview-denied")
    _mock_user(monkeypatch, "user-without-preview")

    resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )

    _assert_no_permission(resp)


def test_preview_course_info_rejects_inactive_or_unknown_permission(
    monkeypatch, test_client, app
):
    shifu_bid = "preview-permission-inactive"
    owner_bid = "owner-preview-inactive"
    inactive_user_bid = "user-preview-inactive"
    unknown_permission_user_bid = "user-preview-unknown-permission"
    _seed_course(app, shifu_bid, owner_bid)
    _add_course_auth(
        app,
        shifu_bid=shifu_bid,
        user_bid=inactive_user_bid,
        auth_type=["view"],
        status=0,
    )
    _add_course_auth(
        app,
        shifu_bid=shifu_bid,
        user_bid=unknown_permission_user_bid,
        auth_type=["delete"],
        status=1,
    )

    _mock_user(monkeypatch, inactive_user_bid)
    inactive_resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    _assert_no_permission(inactive_resp)

    _mock_user(monkeypatch, unknown_permission_user_bid)
    unknown_permission_resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    _assert_no_permission(unknown_permission_resp)


def test_preview_course_info_allows_publish_collaborator(monkeypatch, test_client, app):
    shifu_bid = "preview-permission-publish"
    owner_bid = "owner-preview-publish"
    collaborator_bid = "user-preview-publish"
    _seed_course(app, shifu_bid, owner_bid)
    _add_course_auth(
        app,
        shifu_bid=shifu_bid,
        user_bid=collaborator_bid,
        auth_type=["publish"],
    )
    _mock_user(monkeypatch, collaborator_bid)

    resp = test_client.get(
        f"/api/learn/shifu/{shifu_bid}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["bid"] == shifu_bid


def test_non_preview_course_info_keeps_anonymous_access(monkeypatch, test_client, app):
    shifu_bid = "preview-permission-non-preview"
    _seed_course(app, shifu_bid, "owner-non-preview")
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: (_ for _ in ()).throw(
            AssertionError("non-preview course info should bypass auth")
        ),
        raising=False,
    )

    resp = test_client.get(f"/api/learn/shifu/{shifu_bid}?preview_mode=false")
    payload = resp.get_json(force=True)

    assert resp.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["bid"] == shifu_bid


def test_editor_preview_denied_before_admission_and_stream(
    monkeypatch, test_client, app
):
    shifu_bid = "preview-permission-editor-denied"
    _seed_course(app, shifu_bid, "owner-preview-editor")
    _mock_user(monkeypatch, "user-preview-editor-denied")
    monkeypatch.setattr(
        "flaskr.service.learn.routes.admit_creator_usage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview admission should not run without permission")
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.context_v2.RunScriptPreviewContextV2.stream_preview",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview stream should not run without permission")
        ),
    )

    resp = test_client.post(
        f"/api/learn/shifu/{shifu_bid}/preview/outline-1",
        json={"content": "hello", "block_index": 0},
        headers={"Token": "test-token"},
    )

    _assert_no_permission(resp)


def test_preview_tts_denied_before_admission_and_stream(monkeypatch, test_client, app):
    shifu_bid = "preview-permission-tts-denied"
    _seed_course(app, shifu_bid, "owner-preview-tts")
    _mock_user(monkeypatch, "user-preview-tts-denied")
    monkeypatch.setattr(
        "flaskr.service.learn.routes.admit_creator_usage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview tts admission should not run without permission")
        ),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.routes.stream_preview_tts_audio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview tts stream should not run without permission")
        ),
    )

    resp = test_client.post(
        f"/api/learn/shifu/{shifu_bid}/tts/preview?preview_mode=true",
        json={"text": "hello"},
        headers={"Token": "test-token"},
    )

    _assert_no_permission(resp)
