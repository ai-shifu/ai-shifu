from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import flaskr.dao as dao


_ROUTES_PATH = Path(__file__).resolve().parents[3] / "flaskr/service/learn/routes.py"
_OWNER_BID = "owner-public-route-tests"
_OUTLINE_BID = "outline-public-route-tests"
_GENERATED_BLOCK_BID = "generated-public-route-tests"

_ROUTE_CASES = (
    {
        "name": "course-info",
        "method": "GET",
        "suffix": "",
        "business": "course-info",
    },
    {
        "name": "outline-tree",
        "method": "GET",
        "suffix": "/outline-item-tree",
        "business": "outline-tree",
    },
    {
        "name": "run-put",
        "method": "PUT",
        "suffix": f"/run/{_OUTLINE_BID}",
        "json": {"input": "hello"},
        "business": "run-put",
        "admission": True,
    },
    {
        "name": "preview-block",
        "method": "POST",
        "suffix": f"/preview/{_OUTLINE_BID}",
        "json": {"content": "hello", "block_index": 0},
        "business": "preview-block",
        "permission": True,
        "admission": True,
    },
    {
        "name": "run-get",
        "method": "GET",
        "suffix": f"/run/{_OUTLINE_BID}",
        "business": "run-get",
    },
    {
        "name": "records-get",
        "method": "GET",
        "suffix": f"/records/{_OUTLINE_BID}",
        "business": "records-get",
    },
    {
        "name": "records-delete",
        "method": "DELETE",
        "suffix": f"/records/{_OUTLINE_BID}",
        "business": "records-delete",
    },
    {
        "name": "feedback-submit",
        "method": "POST",
        "suffix": f"/lesson-feedback/{_OUTLINE_BID}",
        "json": {"score": 5, "comment": "helpful", "mode": "read"},
        "business": "feedback-submit",
    },
    {
        "name": "feedback-list",
        "method": "GET",
        "suffix": "/lesson-feedbacks",
        "business": "feedback-list",
    },
    {
        "name": "generated-post",
        "method": "POST",
        "suffix": f"/generated-contents/{_GENERATED_BLOCK_BID}/like",
        "business": "generated-post",
    },
    {
        "name": "generated-get",
        "method": "GET",
        "suffix": f"/generated-contents/{_GENERATED_BLOCK_BID}",
        "business": "generated-get",
    },
    {
        "name": "generated-tts",
        "method": "POST",
        "suffix": f"/generated-blocks/{_GENERATED_BLOCK_BID}/tts",
        "business": "generated-tts",
        "admission": True,
    },
    {
        "name": "preview-tts",
        "method": "POST",
        "suffix": "/tts/preview?preview_mode=true",
        "json": {"text": "hello"},
        "business": "preview-tts",
        "permission": True,
        "admission": True,
    },
)

_PUBLIC_NON_PREVIEW_CASES = tuple(
    case
    for case in _ROUTE_CASES
    if case["name"] not in {"preview-block", "preview-tts", "feedback-list"}
)

_DRAFT_PREVIEW_CASES = (
    {**_ROUTE_CASES[0], "suffix": "?preview_mode=true", "permission": True},
    {
        **_ROUTE_CASES[1],
        "suffix": "/outline-item-tree?preview_mode=true",
        "permission": True,
    },
    {
        **_ROUTE_CASES[2],
        "suffix": f"/run/{_OUTLINE_BID}?preview_mode=true",
        "permission": True,
    },
    {
        **_ROUTE_CASES[5],
        "suffix": f"/records/{_OUTLINE_BID}?preview_mode=true",
        "permission": True,
    },
    {
        **_ROUTE_CASES[10],
        "suffix": (f"/generated-contents/{_GENERATED_BLOCK_BID}?preview_mode=true"),
        "permission": True,
    },
    {
        **_ROUTE_CASES[11],
        "suffix": (f"/generated-blocks/{_GENERATED_BLOCK_BID}/tts?preview_mode=true"),
        "permission": True,
    },
    _ROUTE_CASES[3],
    _ROUTE_CASES[12],
)


def _is_identifier_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Name):
        return decorator.id == "_with_resolved_shifu_identifier"
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Name)
        and decorator.func.id == "_with_resolved_shifu_identifier"
    )


def test_every_shifu_learning_route_resolves_public_identifier_first() -> None:
    module = ast.parse(_ROUTES_PATH.read_text(encoding="utf-8"))
    register = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "register_learn_routes"
    )

    shifu_route_names = []
    for node in register.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        route_decorators = [
            decorator
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "route"
        ]
        if not route_decorators:
            continue
        if not any(
            "/shifu/" in ast.unparse(decorator.args[0])
            for decorator in route_decorators
            if decorator.args
        ):
            continue

        shifu_route_names.append(node.name)
        assert any(
            _is_identifier_decorator(decorator) for decorator in node.decorator_list
        ), f"{node.name} must resolve the public identifier before handling"

    assert len(shifu_route_names) == 13


def _seed_course(
    app,
    *,
    shifu_bid: str,
    slug: str,
    published: bool,
    historical_slug: str | None = None,
    deleted_published_history: bool = False,
) -> None:
    from flaskr.service.shifu.models import (
        DraftOutlineItem,
        DraftShifu,
        PublishedOutlineItem,
        PublishedShifu,
        ShifuCourseSlug,
    )

    with app.app_context():
        ShifuCourseSlug.query.filter_by(shifu_bid=shifu_bid).delete()
        DraftOutlineItem.query.filter_by(shifu_bid=shifu_bid).delete()
        PublishedOutlineItem.query.filter_by(shifu_bid=shifu_bid).delete()
        DraftShifu.query.filter_by(shifu_bid=shifu_bid).delete()
        PublishedShifu.query.filter_by(shifu_bid=shifu_bid).delete()

        course_values = {
            "shifu_bid": shifu_bid,
            "title": "Public Route Course",
            "description": "Course for public route tests",
            "avatar_res_bid": "",
            "keywords": "routes",
            "llm": "gpt-test",
            "llm_temperature": Decimal("0"),
            "llm_system_prompt": "",
            "price": Decimal("0"),
            "created_user_bid": _OWNER_BID,
            "updated_user_bid": _OWNER_BID,
        }
        dao.db.session.add(DraftShifu(**course_values))
        dao.db.session.add(
            DraftOutlineItem(
                shifu_bid=shifu_bid,
                outline_item_bid=_OUTLINE_BID,
                title="Test lesson",
                content="Test lesson content",
                created_user_bid=_OWNER_BID,
                updated_user_bid=_OWNER_BID,
            )
        )
        if published or deleted_published_history:
            dao.db.session.add(
                PublishedShifu(
                    **course_values,
                    deleted=0 if published else 1,
                )
            )
        if published:
            dao.db.session.add(
                PublishedOutlineItem(
                    shifu_bid=shifu_bid,
                    outline_item_bid=_OUTLINE_BID,
                    title="Test lesson",
                    content="Test lesson content",
                    created_user_bid=_OWNER_BID,
                    updated_user_bid=_OWNER_BID,
                )
            )
        slug_bindings = []
        if historical_slug:
            from flaskr.util.datetime import now_utc

            slug_bindings.append(
                ShifuCourseSlug(
                    shifu_bid=shifu_bid,
                    slug=historical_slug,
                    version=1,
                    is_current=None,
                    generation_source="manual",
                    retired_at=now_utc(),
                )
            )
        slug_bindings.append(
            ShifuCourseSlug(
                shifu_bid=shifu_bid,
                slug=slug,
                version=2 if historical_slug else 1,
                is_current=1,
                generation_source="llm",
            )
        )
        dao.db.session.add_all(slug_bindings)
        dao.db.session.commit()


def _mock_user(monkeypatch, *, user_bid: str = _OWNER_BID) -> SimpleNamespace:
    user = SimpleNamespace(
        user_id=user_bid,
        is_creator=True,
        is_operator=False,
        language="en-US",
    )
    monkeypatch.setattr(
        "flaskr.route.user.validate_user",
        lambda _app, _token: user,
        raising=False,
    )
    return user


def _patch_route_dependencies(monkeypatch, *, owner_bid: str = _OWNER_BID):
    from flaskr.service.learn import routes
    from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2

    calls = {
        "business": [],
        "context": [],
        "permission": [],
        "admission": [],
    }

    def record(label: str, shifu_bid: str):
        calls["business"].append((label, shifu_bid))
        return {"route": label}

    monkeypatch.setattr(
        "flaskr.common.shifu_context._get_shifu_creator_bid_cached",
        lambda _app, shifu_bid: calls["context"].append(shifu_bid) or owner_bid,
    )
    monkeypatch.setattr(
        routes,
        "require_shifu_preview_permission",
        lambda _app, _user_bid, shifu_bid: calls["permission"].append(shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "resolve_preview_request_user",
        lambda _app: SimpleNamespace(user_id=owner_bid),
    )
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_args: False)
    monkeypatch.setattr(
        routes,
        "admit_creator_usage",
        lambda _app, *, shifu_bid, usage_scene: calls["admission"].append(
            (shifu_bid, usage_scene)
        ),
    )

    monkeypatch.setattr(
        routes,
        "get_shifu_info",
        lambda _app, shifu_bid, _preview_mode: record("course-info", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "get_outline_item_tree",
        lambda _app, shifu_bid, _user_bid, _preview_mode: record(
            "outline-tree", shifu_bid
        ),
    )

    def run_script(*, shifu_bid, **_kwargs):
        record("run-put", shifu_bid)
        yield 'data: {"type":"done","event_type":"done","content":""}\n\n'

    monkeypatch.setattr(routes, "run_script", run_script)

    def stream_preview(self, *, shifu_bid, **_kwargs):
        del self
        record("preview-block", shifu_bid)
        yield {"type": "done", "event_type": "done", "content": ""}

    monkeypatch.setattr(RunScriptPreviewContextV2, "stream_preview", stream_preview)
    monkeypatch.setattr(
        routes,
        "get_run_status",
        lambda _app, shifu_bid, _outline_bid, _user_bid: record("run-get", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "get_listen_element_record",
        lambda _app, shifu_bid, *_args, **_kwargs: record("records-get", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "reset_learn_record",
        lambda _app, shifu_bid, _outline_bid, _user_bid: record(
            "records-delete", shifu_bid
        ),
    )
    monkeypatch.setattr(
        routes,
        "submit_lesson_feedback",
        lambda _app, *, shifu_bid, **_kwargs: record("feedback-submit", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "list_lesson_feedbacks",
        lambda _app, *, shifu_bid, **_kwargs: record("feedback-list", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "handle_reaction",
        lambda _app, shifu_bid, *_args: record("generated-post", shifu_bid),
    )
    monkeypatch.setattr(
        routes,
        "get_generated_content",
        lambda _app, shifu_bid, *_args: record("generated-get", shifu_bid),
    )

    def stream_generated_block_audio(_app, *, shifu_bid, **_kwargs):
        record("generated-tts", shifu_bid)
        yield {"type": "done", "event_type": "done", "content": ""}

    monkeypatch.setattr(
        routes, "stream_generated_block_audio", stream_generated_block_audio
    )

    def stream_preview_tts_audio(_app, *, shifu_bid, **_kwargs):
        record("preview-tts", shifu_bid)
        yield {"type": "done", "event_type": "done", "content": ""}

    monkeypatch.setattr(routes, "stream_preview_tts_audio", stream_preview_tts_audio)
    return calls


def _request_route(test_client, case: dict, identifier: str):
    response = test_client.open(
        f"/api/learn/shifu/{identifier}{case['suffix']}",
        method=case["method"],
        json=case.get("json"),
        headers={"Token": "test-token"},
    )
    # Streaming route business functions execute while the response is consumed.
    _ = response.data
    return response


@pytest.mark.parametrize(
    "case", _ROUTE_CASES, ids=[case["name"] for case in _ROUTE_CASES]
)
@pytest.mark.parametrize("identifier_kind", ("slug", "historical-slug", "bid"))
def test_learning_routes_pass_canonical_bid_to_context_permission_and_business(
    monkeypatch,
    test_client,
    app,
    case,
    identifier_kind,
):
    case_index = next(
        index for index, candidate in enumerate(_ROUTE_CASES) if candidate is case
    )
    shifu_bid = f"public-route-{case_index:02d}-bid"
    slug = f"canonical-public-route-{case_index:02d}"
    historical_slug = f"historical-public-route-{case_index:02d}"
    _seed_course(
        app,
        shifu_bid=shifu_bid,
        slug=slug,
        historical_slug=historical_slug,
        published=True,
    )
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    identifier = {
        "slug": slug,
        "historical-slug": historical_slug,
        "bid": shifu_bid,
    }[identifier_kind]
    response = _request_route(test_client, case, identifier)

    assert response.status_code == 200
    assert calls["business"] == [(case["business"], shifu_bid)]
    assert calls["context"] == [shifu_bid]
    assert calls["permission"] == ([shifu_bid] if case.get("permission") else [])
    assert [bid for bid, _scene in calls["admission"]] == (
        [shifu_bid] if case.get("admission") else []
    )


@pytest.mark.parametrize(
    "case",
    _PUBLIC_NON_PREVIEW_CASES,
    ids=[case["name"] for case in _PUBLIC_NON_PREVIEW_CASES],
)
@pytest.mark.parametrize("identifier_kind", ("slug", "bid"))
@pytest.mark.parametrize("published_history", ("missing", "deleted"))
def test_unpublished_courses_are_rejected_before_context_admission_and_business(
    monkeypatch,
    test_client,
    app,
    case,
    identifier_kind,
    published_history,
):
    case_index = next(
        index for index, candidate in enumerate(_ROUTE_CASES) if candidate is case
    )
    shifu_bid = f"draft-route-{case_index:02d}-bid"
    slug = f"unpublished-public-route-{case_index:02d}"
    _seed_course(
        app,
        shifu_bid=shifu_bid,
        slug=slug,
        published=False,
        deleted_published_history=published_history == "deleted",
    )
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    identifier = slug if identifier_kind == "slug" else shifu_bid
    response = _request_route(test_client, case, identifier)
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 4008
    assert calls == {
        "business": [],
        "context": [],
        "permission": [],
        "admission": [],
    }


@pytest.mark.parametrize(
    "case", _ROUTE_CASES, ids=[case["name"] for case in _ROUTE_CASES]
)
def test_unknown_identifiers_are_rejected_before_context_admission_and_business(
    monkeypatch,
    test_client,
    case,
):
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    response = _request_route(test_client, case, "missing-public-course-route")
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 4008
    assert calls == {
        "business": [],
        "context": [],
        "permission": [],
        "admission": [],
    }


@pytest.mark.parametrize(
    "case",
    _DRAFT_PREVIEW_CASES,
    ids=[case["name"] for case in _DRAFT_PREVIEW_CASES],
)
@pytest.mark.parametrize("identifier_kind", ("slug", "bid"))
def test_preview_routes_allow_drafts_after_canonical_resolution(
    monkeypatch,
    test_client,
    app,
    case,
    identifier_kind,
):
    case_index = next(
        index
        for index, candidate in enumerate(_DRAFT_PREVIEW_CASES)
        if candidate is case
    )
    shifu_bid = f"preview-route-{case_index:02d}-bid"
    slug = f"draft-preview-course-route-{case_index:02d}"
    _seed_course(app, shifu_bid=shifu_bid, slug=slug, published=False)
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    identifier = slug if identifier_kind == "slug" else shifu_bid
    response = _request_route(test_client, case, identifier)

    assert response.status_code == 200
    assert calls["business"] == [(case["business"], shifu_bid)]
    assert calls["context"] == [shifu_bid]
    assert calls["permission"] == [shifu_bid]
    assert [bid for bid, _scene in calls["admission"]] == (
        [shifu_bid] if case.get("admission") else []
    )


@pytest.mark.parametrize("identifier_kind", ("slug", "bid"))
def test_teacher_feedback_list_keeps_draft_access(
    monkeypatch,
    test_client,
    app,
    identifier_kind,
):
    shifu_bid = f"draft-feedback-{identifier_kind}-bid"
    slug = f"draft-feedback-course-{identifier_kind}"
    _seed_course(app, shifu_bid=shifu_bid, slug=slug, published=False)
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    identifier = slug if identifier_kind == "slug" else shifu_bid
    response = _request_route(test_client, _ROUTE_CASES[8], identifier)

    assert response.status_code == 200
    assert calls["business"] == [("feedback-list", shifu_bid)]
    assert calls["context"] == [shifu_bid]


@pytest.mark.parametrize("identifier_kind", ("slug", "bid"))
@pytest.mark.parametrize(
    ("actor_bid", "is_creator"),
    (
        ("draft-feedback-non-owner", True),
        (_OWNER_BID, False),
    ),
    ids=("non-owner", "non-creator-owner"),
)
def test_teacher_feedback_list_rejects_unauthorized_draft_access(
    monkeypatch,
    test_client,
    app,
    identifier_kind,
    actor_bid,
    is_creator,
):
    actor_kind = "creator" if is_creator else "teacher-account-disabled"
    shifu_bid = f"protected-draft-feedback-{identifier_kind}-{actor_kind}"
    slug = f"protected-draft-feedback-course-{identifier_kind}-{actor_kind}"
    _seed_course(app, shifu_bid=shifu_bid, slug=slug, published=False)
    user = _mock_user(monkeypatch, user_bid=actor_bid)
    user.is_creator = is_creator
    calls = _patch_route_dependencies(monkeypatch)

    identifier = slug if identifier_kind == "slug" else shifu_bid
    response = _request_route(test_client, _ROUTE_CASES[8], identifier)
    payload = response.get_json(force=True)

    assert response.status_code == 200
    assert payload["code"] == 401
    assert calls["business"] == []
    assert calls["permission"] == []
    assert calls["admission"] == []


@pytest.mark.parametrize("identifier_kind", ("slug", "bid"))
def test_preview_query_does_not_bypass_routes_without_preview_semantics(
    monkeypatch,
    test_client,
    app,
    identifier_kind,
):
    shifu_bid = f"draft-run-status-{identifier_kind}"
    slug = f"draft-run-status-course-{identifier_kind}"
    _seed_course(app, shifu_bid=shifu_bid, slug=slug, published=False)
    _mock_user(monkeypatch)
    calls = _patch_route_dependencies(monkeypatch)

    identifier = slug if identifier_kind == "slug" else shifu_bid
    response = test_client.get(
        f"/api/learn/shifu/{identifier}/run/{_OUTLINE_BID}?preview_mode=true",
        headers={"Token": "test-token"},
    )
    payload = response.get_json(force=True)

    assert payload["code"] == 4008
    assert calls["context"] == []
    assert calls["business"] == []
