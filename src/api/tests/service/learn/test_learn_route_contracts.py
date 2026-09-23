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
from flaskr.service.learn.models import LearnLessonFeedback, LearnProgressRecord
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ({}, None),
        ({"empty": [], "missing": None}, None),
        (
            {1: [None, 0, False, "answer"], "name": "Ada"},
            {"1": ["0", "False", "answer"], "name": ["Ada"]},
        ),
        ([None, "answer", 0], {"user_input": ["answer", "0"]}),
        ([None], None),
        (False, {"user_input": ["False"]}),
        ("answer", {"user_input": ["answer"]}),
    ],
)
def test_legacy_input_normalization_preserves_answer_values(
    value: object, expected: object
) -> None:
    assert routes._normalize_user_input(value) == expected


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


@pytest.mark.parametrize("visual", [None, " true "])
def test_preview_route_supports_legacy_aliases_and_validates_before_model_call(
    monkeypatch: object, test_client: object, feedback_course: object, visual: object
) -> None:
    preview = Mock(return_value=iter([{"type": "done"}]))
    monkeypatch.setattr(routes.RunScriptPreviewContextV2, "stream_preview", preview)
    monkeypatch.setattr(routes, "is_builtin_demo_shifu", lambda *_: True)
    monkeypatch.setattr(routes, "require_shifu_preview_permission", Mock())
    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/lesson",
        json={
            "prompt": "Lesson text",
            "blockIndex": 0,
            "input": ["answer", None],
            "visual_mode": visual,
        },
        headers={"Token": "test-token", "Session-Id": "preview-session"},
    )
    assert '"type": "done"' in response.get_data(as_text=True)
    args = preview.call_args.kwargs
    assert args["session_id"] == "preview-session"
    assert args["preview_request"].user_input == {"user_input": ["answer"]}
    assert args["preview_request"].visual_mode is (visual is not None)
    preview.reset_mock()
    response = test_client.post(
        f"/api/learn/shifu/{feedback_course.bid}/preview/lesson",
        json={"content": "Lesson", "block_index": "invalid"},
        headers={"Token": "test-token"},
    ).get_json(force=True)
    assert response["code"] == ERROR_CODE["server.common.paramsError"]
    preview.assert_not_called()
