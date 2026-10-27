"""Exercise learning HTTP permissions, input normalization, and stream cleanup."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import routes
from flaskr.service.learn.models import (
    LearnLessonFeedback,
    LearnLessonResetRecord,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
)


@pytest.fixture
def feedback_course(app: object, monkeypatch: object) -> object:
    identity = uuid.uuid4().hex
    user = SimpleNamespace(
        user_id=identity, is_creator=True, is_operator=False, language="en-US"
    )
    monkeypatch.setattr("flaskr.route.user.validate_user", lambda *_: user)
    monkeypatch.setattr(
        routes, "get_shifu_context_snapshot", lambda: {"shifu_creator_bid": identity}
    )
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=identity,
                shifu_bid=identity,
                outline_item_bid=identity,
                user_bid=identity,
                status=LEARN_STATUS_COMPLETED,
                deleted=0,
            )
        )
        db.session.add(
            DraftShifu(
                shifu_bid=identity,
                created_user_bid=identity,
                updated_user_bid=identity,
                title="Feedback course",
                deleted=0,
            )
        )
        for model in (DraftOutlineItem, PublishedOutlineItem):
            db.session.add(
                model(
                    shifu_bid=identity,
                    outline_item_bid=identity,
                    title="Feedback lesson",
                    position=0,
                    deleted=0,
                )
            )
    yield SimpleNamespace(bid=identity, user=user)
    with app.app_context(), unit_of_work():
        for model in (
            LearnLessonFeedback,
            LearnProgressRecord,
            DraftOutlineItem,
            PublishedOutlineItem,
            DraftShifu,
        ):
            model.query.filter_by(shifu_bid=identity).delete()


def _request_feedback(client: object, course: object, **kwargs: object) -> object:
    return client.post(
        f"/api/learn/shifu/{course.bid}/lesson-feedback/{course.bid}",
        headers={"Token": "test-token"},
        **kwargs,
    ).get_json(force=True)


def _progress_snapshot(app: object) -> list[tuple[object, ...]]:
    with app.app_context():
        return [
            (
                row.progress_record_bid,
                row.shifu_bid,
                row.outline_item_bid,
                row.user_bid,
                row.status,
                row.deleted,
            )
            for row in LearnProgressRecord.query.order_by(LearnProgressRecord.id).all()
        ]


@pytest.mark.parametrize("published_only", [False, True])
def test_feedback_http_round_trip_preserves_scope_and_updates_existing_submission(
    app: object, test_client: object, feedback_course: object, published_only: bool
) -> None:
    if published_only:
        with app.app_context(), unit_of_work():
            DraftOutlineItem.query.filter_by(shifu_bid=feedback_course.bid).delete()
    first = _request_feedback(
        test_client,
        feedback_course,
        json={"score": 3, "comment": " First attempt ", "mode": "listen"},
    )
    assert first["code"] == 0
    second = _request_feedback(
        test_client, feedback_course, json={"score": 5, "comment": "Now clear"}
    )
    assert second["code"] == 0
    assert second["data"]["lesson_feedback_bid"] == first["data"]["lesson_feedback_bid"]
    response = test_client.get(
        f"/api/learn/shifu/{feedback_course.bid}/lesson-feedbacks",
        query_string={
            "outline_bid": feedback_course.bid,
            "page_index": 1,
            "page_size": 1,
        },
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == 0
    assert response["data"]["total"] == 1
    item = response["data"]["items"][0]
    assert item["score"] == 5
    assert item["comment"] == "Now clear"
    assert item["mode"] == "read"
    assert item["user_bid"] == feedback_course.user.user_id
    assert item["outline_bid"] == feedback_course.bid


@pytest.mark.parametrize(
    "payload",
    [[1], {"score": 0}, {"score": 6}, {"score": "bad"}, {"score": 3, "mode": "bad"}],
)
def test_invalid_feedback_does_not_create_a_submission(
    app: object, test_client: object, feedback_course: object, payload: object
) -> None:
    response = _request_feedback(test_client, feedback_course, json=payload)
    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    with app.app_context():
        assert (
            LearnLessonFeedback.query.filter_by(shifu_bid=feedback_course.bid).count()
            == 0
        )


@pytest.mark.parametrize("deleted", [False, True])
def test_feedback_rejects_lessons_outside_the_active_course(
    app: object, test_client: object, feedback_course: object, deleted: bool
) -> None:
    with app.app_context(), unit_of_work():
        for model in (DraftOutlineItem, PublishedOutlineItem):
            row = model.query.filter_by(shifu_bid=feedback_course.bid).one()
            if deleted:
                row.deleted = 1
            else:
                row.outline_item_bid = "different-outline"
    response = _request_feedback(test_client, feedback_course, json={"score": 5})
    assert response["code"] == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
    with app.app_context():
        assert (
            LearnLessonFeedback.query.filter_by(shifu_bid=feedback_course.bid).count()
            == 0
        )


@pytest.mark.parametrize(
    ("creator", "owner", "error_key"),
    [
        (False, "owner", "server.shifu.noPermission"),
        (True, "other-owner", "server.shifu.noPermission"),
        (True, None, "server.shifu.shifuNotFound"),
    ],
)
def test_feedback_list_requires_the_course_owner(
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    creator: bool,
    owner: str | None,
    error_key: str,
) -> None:
    feedback_course.user.is_creator = creator
    resolved_owner = feedback_course.bid if owner == "owner" else owner
    monkeypatch.setattr(routes, "get_shifu_context_snapshot", dict)
    monkeypatch.setattr(routes, "get_shifu_creator_bid", lambda *_: resolved_owner)
    listing = Mock()
    monkeypatch.setattr(routes, "list_lesson_feedbacks", listing)
    response = test_client.get(
        f"/api/learn/shifu/{feedback_course.bid}/lesson-feedbacks",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE[error_key]
    listing.assert_not_called()


@pytest.mark.parametrize(
    "query", ["page_index=bad", "page_size=bad", "page_index=0", "page_size=-1"]
)
def test_feedback_list_rejects_invalid_pagination_before_querying(
    monkeypatch: object, test_client: object, feedback_course: object, query: str
) -> None:
    listing = Mock()
    monkeypatch.setattr(routes, "list_lesson_feedbacks", listing)
    response = test_client.get(
        f"/api/learn/shifu/{feedback_course.bid}/lesson-feedbacks?{query}",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    listing.assert_not_called()


@pytest.mark.parametrize("business_error", [False, True])
def test_sse_failure_preserves_partial_output_then_error_and_terminal_order(
    monkeypatch: object, business_error: bool
) -> None:
    app = Flask(__name__)
    remove = Mock()
    monkeypatch.setattr(
        routes, "db", SimpleNamespace(session=SimpleNamespace(remove=remove))
    )
    error = (
        AppError("declined", 4321) if business_error else ValueError("broken stream")
    )

    def messages() -> object:
        yield {"type": "delta", "content": "partial"}
        raise error

    with app.test_request_context():
        response = routes._stream_sse_response(
            app,
            message_iter_factory=messages,
            close_log="closed",
            error_log="failed",
            error_event_factory=lambda exc: {"type": "error", "content": str(exc)},
            terminal_event_factory=lambda: {"type": "done"},
        )
        assert remove.call_count == 1
        events = [json.loads(line.removeprefix("data: ")) for line in response.response]
    assert events == [
        {"type": "delta", "content": "partial"},
        {"type": "error", "content": str(error)},
        {"type": "done"},
    ]
    assert remove.call_count == 2


@pytest.mark.parametrize(
    "error", [ValueError("provider unavailable"), RuntimeError("worker failed")]
)
def test_passthrough_reraises_worker_failures_after_releasing_session(
    monkeypatch: object, error: Exception
) -> None:
    app = Flask(__name__)
    remove = Mock()
    monkeypatch.setattr(
        routes, "db", SimpleNamespace(session=SimpleNamespace(remove=remove))
    )

    def messages() -> object:
        yield "data: partial\n\n"
        raise error

    with app.test_request_context():
        response = routes._stream_passthrough_response(
            app,
            message_iter_factory=messages,
            close_log="closed",
            error_log="failed",
        )
        stream = iter(response.response)
        assert next(stream) == "data: partial\n\n"
        with pytest.raises(type(error), match=str(error)):
            next(stream)
    assert remove.call_count == 2


def test_generated_content_and_reaction_routes_forward_authenticated_scope(
    monkeypatch: object, test_client: object, feedback_course: object
) -> None:
    course = feedback_course.bid
    content = Mock(return_value={"position": 4})
    reaction = Mock(return_value=True)
    permission = Mock()
    monkeypatch.setattr(routes, "get_generated_content", content)
    monkeypatch.setattr(routes, "handle_reaction", reaction)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", permission)
    response = test_client.get(
        f"/api/learn/shifu/{course}/generated-contents/block?preview_mode=TRUE",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["data"] == {"position": 4}
    assert content.call_args.args[1:] == (course, "block", course, True)
    assert permission.call_args.args[1:] == (course, course)
    response = test_client.post(
        f"/api/learn/shifu/{course}/generated-contents/block/like",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["data"] is True
    assert reaction.call_args.args[1:] == (course, course, "block", "like")


def test_record_reset_route_uses_authenticated_learner(
    monkeypatch: object, test_client: object, feedback_course: object
) -> None:
    reset = Mock(return_value=True)
    monkeypatch.setattr(routes, "reset_learn_record", reset)
    response = test_client.delete(
        f"/api/learn/shifu/{feedback_course.bid}/records/lesson",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["data"] is True
    assert reset.call_args.args[1:] == (
        feedback_course.bid,
        "lesson",
        feedback_course.bid,
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_preview_reset_checks_permission_before_scoped_reset(
    monkeypatch: object, test_client: object, feedback_course: object, allowed: bool
) -> None:
    preview_user = "preview-reset-user"
    feedback_course.user.user_id = preview_user
    reset = Mock(return_value=True)
    permission = Mock()
    if not allowed:
        permission.side_effect = lambda *_args: routes.raise_error(
            "server.shifu.shifuNotFound"
        )
    monkeypatch.setattr(routes, "reset_learn_record", reset)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", permission)
    response = test_client.delete(
        f"/api/learn/shifu/{feedback_course.bid}/records/lesson?preview_mode=TRUE",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert permission.call_args.args[1:] == (preview_user, feedback_course.bid)
    if allowed:
        assert response["data"] is True
        assert reset.call_args.kwargs == {
            "preview_mode": True,
            "reset_request_id": None,
        }
    else:
        assert response["code"] != 0
        reset.assert_not_called()


@pytest.mark.parametrize("preview", [False, True])
def test_generated_audio_route_admits_billing_and_serializes_provider_errors(
    monkeypatch: object, test_client: object, feedback_course: object, preview: bool
) -> None:
    course = feedback_course.bid
    permission, production_admission, preview_admission = Mock(), Mock(), Mock()
    monkeypatch.setattr(routes, "require_shifu_preview_permission", permission)
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_: False)
    monkeypatch.setattr(routes, "admit_creator_usage", production_admission)
    monkeypatch.setattr(routes, "admit_creator_preview_usage", preview_admission)
    provider = Mock(side_effect=AppError("audio quota exhausted", 4321))
    monkeypatch.setattr(routes, "stream_generated_block_audio", provider)
    response = test_client.post(
        f"/api/learn/shifu/{course}/generated-blocks/block/tts",
        query_string={"preview_mode": str(preview), "listen": "true"},
        headers={"Token": "test-token"},
    )
    assert response.mimetype == "text/event-stream"
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.get_data(as_text=True).split("\n\n")
        if line
    ]
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["content"] == "audio quota exhausted"
    assert events[0]["generated_block_bid"] == "block"
    assert provider.call_args.kwargs == {
        "shifu_bid": course,
        "generated_block_bid": "block",
        "user_bid": course,
        "preview_mode": preview,
        "listen": True,
    }
    assert permission.call_count == int(preview)
    assert preview_admission.call_count == int(preview)
    assert production_admission.call_count == int(not preview)


@pytest.mark.parametrize("listen", [None, " true "])
def test_runtime_route_normalizes_listen_and_learning_mode_before_streaming(
    monkeypatch: object, test_client: object, feedback_course: object, listen: object
) -> None:
    run = Mock(return_value=iter(["data: completed\n\n"]))
    monkeypatch.setattr(routes, "run_script", run)
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_: True)
    response = test_client.put(
        f"/api/learn/shifu/{feedback_course.bid}/run/{feedback_course.bid}",
        json={
            "listen": listen,
            "learning_mode": " classroom ",
            "input": {"answer": ["yes"]},
        },
        headers={"Token": "test-token"},
    )
    assert response.get_data(as_text=True) == "data: completed\n\n"
    assert run.call_args.kwargs["listen"] is (listen is not None)
    assert run.call_args.kwargs["learning_mode"] == "classroom"
    assert run.call_args.kwargs["user_input"] == {"answer": ["yes"]}


@pytest.mark.parametrize("preview_mode", [False, True])
def test_runtime_route_rejects_a_lesson_from_another_course_before_admission(
    app: object,
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    preview_mode: bool,
) -> None:
    foreign_course_bid = uuid.uuid4().hex
    foreign_outline_bid = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        for model in (DraftOutlineItem, PublishedOutlineItem):
            db.session.add(
                model(
                    shifu_bid=foreign_course_bid,
                    outline_item_bid=foreign_outline_bid,
                    title="Foreign lesson",
                    position=0,
                    deleted=0,
                )
            )

    preview_admission = Mock()
    production_admission = Mock()
    run = Mock(return_value=iter(["data: completed\n\n"]))
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_: False)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    monkeypatch.setattr(routes, "admit_creator_preview_usage", preview_admission)
    monkeypatch.setattr(routes, "admit_creator_usage", production_admission)
    monkeypatch.setattr(routes, "run_script", run)
    progress_before = _progress_snapshot(app)

    try:
        response = test_client.put(
            f"/api/learn/shifu/{feedback_course.bid}/run/{foreign_outline_bid}",
            query_string={"preview_mode": str(preview_mode).lower()},
            json={
                "input": "answer",
                # Payload identifiers must never override the route's course scope.
                "shifu_bid": foreign_course_bid,
                "outline_bid": foreign_outline_bid,
            },
            headers={"Token": "test-token"},
        ).get_json(force=True)
    finally:
        with app.app_context(), unit_of_work():
            for model in (DraftOutlineItem, PublishedOutlineItem):
                model.query.filter_by(outline_item_bid=foreign_outline_bid).delete()

    assert response["code"] == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
    assert _progress_snapshot(app) == progress_before
    preview_admission.assert_not_called()
    production_admission.assert_not_called()
    run.assert_not_called()


@pytest.mark.parametrize("preview_mode", [False, True])
def test_runtime_route_rejects_soft_deleted_lessons_without_persisting(
    app: object,
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    preview_mode: bool,
) -> None:
    with app.app_context(), unit_of_work():
        selected_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
        selected_model.query.filter_by(shifu_bid=feedback_course.bid).one().deleted = 1

    preview_admission = Mock()
    production_admission = Mock()
    run = Mock(return_value=iter(["data: completed\n\n"]))
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    monkeypatch.setattr(routes, "admit_creator_preview_usage", preview_admission)
    monkeypatch.setattr(routes, "admit_creator_usage", production_admission)
    monkeypatch.setattr(routes, "run_script", run)
    progress_before = _progress_snapshot(app)

    response = test_client.put(
        f"/api/learn/shifu/{feedback_course.bid}/run/{feedback_course.bid}",
        query_string={"preview_mode": str(preview_mode).lower()},
        json={"input": "answer"},
        headers={"Token": "test-token"},
    ).get_json(force=True)

    assert response["code"] == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
    assert _progress_snapshot(app) == progress_before
    preview_admission.assert_not_called()
    production_admission.assert_not_called()
    run.assert_not_called()


@pytest.mark.parametrize("preview_mode", [False, True])
def test_runtime_route_rejects_a_lesson_missing_from_the_requested_version(
    app: object,
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    preview_mode: bool,
) -> None:
    with app.app_context(), unit_of_work():
        unavailable_model = DraftOutlineItem if preview_mode else PublishedOutlineItem
        unavailable_model.query.filter_by(shifu_bid=feedback_course.bid).delete()

    preview_admission = Mock()
    production_admission = Mock()
    run = Mock(return_value=iter(["data: completed\n\n"]))
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    monkeypatch.setattr(routes, "admit_creator_preview_usage", preview_admission)
    monkeypatch.setattr(routes, "admit_creator_usage", production_admission)
    monkeypatch.setattr(routes, "run_script", run)

    response = test_client.put(
        f"/api/learn/shifu/{feedback_course.bid}/run/{feedback_course.bid}",
        query_string={"preview_mode": str(preview_mode).lower()},
        json={"input": "answer"},
        headers={"Token": "test-token"},
    ).get_json(force=True)

    assert response["code"] == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
    preview_admission.assert_not_called()
    production_admission.assert_not_called()
    run.assert_not_called()


def test_preview_route_reads_only_current_fields_and_validates_before_model_call(
    monkeypatch: object, test_client: object, feedback_course: object
) -> None:
    from flaskr.service.learn.agent import debug_session

    preview = Mock(return_value=iter([{"type": "done"}]))
    monkeypatch.setattr(debug_session, "stream_debug_preview", preview)
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_: True)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/lesson",
        json={
            "content": "Lesson text",
            "block_index": 0,
            "user_input": {"choice": ["answer"]},
            # Retired fields no editor bundle sends any more; they are ignored.
            "context": [{"role": "user", "content": "old"}],
            "document_prompt": "old",
            "visual_mode": True,
            "debug_session_id": "editor-run-1",
        },
        headers={"Token": "test-token"},
    )
    assert '"type": "done"' in response.get_data(as_text=True)
    args = preview.call_args.kwargs
    assert args["run_bid"] == "editor-run-1"
    assert args["preview_request"].get_document() == "Lesson text"
    assert args["preview_request"].user_input == {"choice": ["answer"]}
    for retired in ("context", "document_prompt", "visual_mode"):
        assert not hasattr(args["preview_request"], retired)
    preview.reset_mock()

    # The pre-2.0 aliases are no longer read, so such a payload lacks block_index.
    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/lesson",
        json={
            "prompt": "Lesson text",
            "blockIndex": 0,
            "input": ["answer"],
            "debug_session_id": "editor-run-1",
        },
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    preview.assert_not_called()

    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/lesson",
        json={
            "content": "Lesson",
            "block_index": "invalid",
            "debug_session_id": "editor-run-1",
        },
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    preview.assert_not_called()


@pytest.mark.parametrize(
    "variables",
    [
        None,
        {"language": "en-US"},
        {"sys_user_language": "en-US"},
        {"sys_user_language": "en-US", "language": "zh-CN"},
    ],
)
def test_editor_preview_streams_through_the_agent_with_synchronized_language(
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    variables: dict | None,
) -> None:
    """Route editor sessions to the agent with synchronized language aliases."""
    from flaskr.service.learn.agent import debug_session

    marker = {"type": "preview_engine", "content": "2.0"}
    agent = Mock(return_value=iter([marker]))
    monkeypatch.setattr(debug_session, "stream_debug_preview", agent)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())

    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/{feedback_course.bid}",
        json={
            "content": "Current editor draft",
            "block_index": 0,
            "debug_session_id": "editor-run-1",
            "variables": variables,
        },
        headers={"Token": "test-token", "Accept-Language": "fr-FR"},
    )

    assert '"preview_engine"' in response.get_data(as_text=True)
    assert agent.call_args.kwargs["preview_request"].content == "Current editor draft"
    assert agent.call_args.kwargs["run_bid"] == "editor-run-1"
    expected_language = "en-US" if variables else "fr-FR"
    assert agent.call_args.kwargs["preview_request"].variables == {
        "sys_user_language": expected_language,
        "language": expected_language,
    }


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({}, "fr-FR"),
        ({"sys_user_language": "", "language": ""}, "fr-FR"),
        ({"sys_user_language": "", "language": "zh-CN"}, "fr-FR"),
        ({"sys_user_language": "unknown"}, "fr-FR"),
        ({"sys_user_language": "en-US", "language": "zh-CN"}, "en-US"),
    ],
)
def test_preview_captures_language_before_streaming(
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    variables: dict,
    expected: str,
) -> None:
    """Keep resolved language valid after streaming loses request-local i18n."""
    from flaskr.i18n import clear_language
    from flaskr.service.learn.agent import debug_session
    from flaskr.service.learn.preview_language import resolve_preview_language

    seen = []

    def stream(*_args: object, **kwargs: object) -> object:
        """Observe captured variables after clearing the request language context."""
        clear_language()
        captured = kwargs["preview_request"].variables
        seen.append(resolve_preview_language(captured))
        yield {"type": "done"}

    monkeypatch.setattr(debug_session, "stream_debug_preview", stream)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/{feedback_course.bid}",
        json={
            "content": "Draft",
            "block_index": 0,
            "debug_session_id": "run",
            "variables": variables,
        },
        headers={"Token": "test-token", "Accept-Language": "fr-FR"},
    )
    assert '"done"' in response.get_data(as_text=True)
    assert seen == [expected]


@pytest.mark.parametrize("debug_session_id", [None, "", "not valid!"])
def test_editor_preview_without_a_debug_session_is_refused(
    monkeypatch: object,
    test_client: object,
    feedback_course: object,
    debug_session_id: str | None,
) -> None:
    """Only a bundle old enough to expect the retired 1.0 block preview omits it."""
    from flaskr.service.learn.agent import debug_session

    agent = Mock(return_value=iter([{"type": "done"}]))
    monkeypatch.setattr(debug_session, "stream_debug_preview", agent)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    payload = {"content": "Lesson", "block_index": 0}
    if debug_session_id is not None:
        payload["debug_session_id"] = debug_session_id

    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/{feedback_course.bid}",
        json=payload,
        headers={"Token": "test-token"},
    ).get_json(force=True)

    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    agent.assert_not_called()


@pytest.mark.parametrize("allowed", [True, False])
def test_reset_status_checks_preview_permission_and_keeps_identity(
    monkeypatch: object, test_client: object, feedback_course: object, allowed: bool
) -> None:
    """The availability endpoint cannot turn a preview flag into a learner bypass."""
    reader = "reset-status-reader"
    feedback_course.user.user_id = reader
    availability = Mock(return_value={"can_reset": True})
    permission = Mock()
    if not allowed:
        permission.side_effect = lambda *_args: routes.raise_error(
            "server.shifu.shifuNotFound"
        )
    monkeypatch.setattr(routes, "get_lesson_reset_status", availability)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", permission)
    response = test_client.get(
        f"/api/learn/shifu/{feedback_course.bid}/records/lesson/reset-status?preview_mode=true&user_id=forged",
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert permission.call_args.args[1:] == (reader, feedback_course.bid)
    if allowed:
        assert response["data"] == {"can_reset": True}
        assert availability.call_args.args[1:] == (
            feedback_course.bid,
            "lesson",
            reader,
        )
        assert availability.call_args.kwargs == {"preview_mode": True}
    else:
        assert response["code"] != 0
        availability.assert_not_called()


def test_reset_route_passes_the_client_trace_id_through(
    monkeypatch: object, test_client: object, feedback_course: object
) -> None:
    """The reset receipt reuses the existing trace header instead of a new one."""
    reset = Mock(return_value=True)
    monkeypatch.setattr(routes, "reset_learn_record", reset)
    response = test_client.delete(
        f"/api/learn/shifu/{feedback_course.bid}/records/lesson",
        headers={"Token": "test-token", "X-Request-ID": "existing-client-trace"},
    ).get_json(force=True)
    assert response["data"] is True
    assert reset.call_args.kwargs["reset_request_id"] == "existing-client-trace"


def test_reset_status_reads_recorded_usage_over_http(
    app: object, test_client: object, feedback_course: object, monkeypatch: object
) -> None:
    """A learner over the limit sees can_reset false without any count."""
    learner = "reset-status-learner"
    feedback_course.user.user_id = learner
    monkeypatch.setitem(app.config, "LESSON_RESET_LIMIT", 1)
    monkeypatch.setattr(routes, "get_shifu_context_snapshot", dict)
    url = f"/api/learn/shifu/{feedback_course.bid}/records/{feedback_course.bid}"
    before = test_client.get(
        f"{url}/reset-status", headers={"Token": "test-token"}
    ).get_json(force=True)
    assert before["data"] == {"can_reset": True}
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=learner,
                shifu_bid=feedback_course.bid,
                outline_item_bid=feedback_course.bid,
                user_bid=learner,
                status=LEARN_STATUS_COMPLETED,
                deleted=0,
            )
        )
    first = test_client.delete(url, headers={"Token": "test-token"}).get_json(
        force=True
    )
    assert first["data"] is True
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnProgressRecord(
                progress_record_bid=learner + "-again",
                shifu_bid=feedback_course.bid,
                outline_item_bid=feedback_course.bid,
                user_bid=learner,
                status=LEARN_STATUS_COMPLETED,
                deleted=0,
            )
        )
    after = test_client.get(
        f"{url}/reset-status", headers={"Token": "test-token"}
    ).get_json(force=True)
    assert after["data"] == {"can_reset": False}
    blocked = test_client.delete(url, headers={"Token": "test-token"}).get_json(
        force=True
    )
    assert blocked["code"] == ERROR_CODE["server.learn.resetLimitReached"]
    with app.app_context(), unit_of_work():
        LearnLessonResetRecord.query.filter_by(shifu_bid=feedback_course.bid).delete()
