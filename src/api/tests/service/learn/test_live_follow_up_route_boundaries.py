"""Exercise live follow-up access checks and conversation configuration boundaries."""

from contextlib import nullcontext
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import live_follow_up_routes as live
from flaskr.service.learn.learn_dtos import OutlineType
from flaskr.service.shifu.consts import ASK_MODE_DISABLE

from tests.service.learn import published_course

runtime_dependencies = published_course.runtime_dependencies


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "ftp://learn.example.com",
        "https://user:password@learn.example.com",
        "https://learn.example.com/path",
        "https://learn.example.com?token=secret",
        "https://learn.example.com#fragment",
        "https://[invalid",
        "//learn.example.com",
    ],
)
def test_live_origin_rejects_non_origin_urls(origin: str) -> None:
    assert live._normalize_origin(origin) == ""


@pytest.mark.parametrize(
    "origin", ["http://localhost:3000", "http://127.0.0.1:3000", "http://[::1]:3000"]
)
def test_development_accepts_loopback_browser_origins(
    monkeypatch: object, origin: str
) -> None:
    app = Flask(__name__)
    app.config["ENV"] = "development"
    monkeypatch.setattr(live, "is_allowed_oauth_origin", lambda *_: False)
    with app.test_request_context(
        base_url="https://api.example.com", headers={"Origin": origin}
    ):
        assert live._require_allowed_origin(app) == origin


def test_proxy_transport_and_explicit_allowlist_accept_only_matching_origins(
    monkeypatch: object,
) -> None:
    app = Flask(__name__)
    app.config["ENV"] = "production"
    allowlist = Mock(return_value=False)
    monkeypatch.setattr(live, "is_allowed_oauth_origin", allowlist)
    with app.test_request_context(
        base_url="http://learn.example.com",
        headers={
            "Origin": "https://learn.example.com/",
            "X-Forwarded-Proto": "https, http",
        },
    ):
        assert live._require_allowed_origin(app) == "https://learn.example.com"
    allowlist.assert_not_called()
    allowlist.return_value = True
    with app.test_request_context(
        base_url="https://api.example.com",
        headers={"Origin": "https://teacher.example.com"},
    ):
        assert live._require_allowed_origin(app) == "https://teacher.example.com"
    allowlist.assert_called_once_with(app, "https://teacher.example.com")
    allowlist.return_value = False
    with (
        app.test_request_context(
            base_url="https://api.example.com",
            headers={"Origin": "http://localhost:3000"},
        ),
        pytest.raises(AppError),
    ):
        live._require_allowed_origin(app)


@pytest.mark.parametrize(
    ("preview", "paid", "kind", "permitted"),
    [
        (False, False, OutlineType.NORMAL, False),
        (False, False, OutlineType.TRIAL, True),
        (False, False, OutlineType.GUEST, True),
        (False, True, OutlineType.NORMAL, True),
        (True, False, OutlineType.NORMAL, True),
    ],
)
def test_live_course_access_respects_nested_lesson_payment_and_preview_permission(
    monkeypatch: object, preview: bool, paid: bool, kind: OutlineType, permitted: bool
) -> None:
    app = Flask(__name__)
    lesson = SimpleNamespace(bid="lesson", children=[], is_paid=paid, type=kind)
    parent = SimpleNamespace(bid="chapter", children=[lesson])
    tree = Mock(return_value=SimpleNamespace(outline_items=[parent]))
    permission = Mock()
    monkeypatch.setattr(live, "get_outline_item_tree", tree)
    monkeypatch.setattr(live, "require_shifu_preview_permission", permission)
    args = {
        "shifu_bid": "course",
        "outline_bid": "lesson",
        "user_bid": "learner",
        "preview_mode": preview,
    }
    if permitted:
        live._require_course_access(app, **args)
    else:
        with pytest.raises(AppError) as error:
            live._require_course_access(app, **args)
        assert error.value.code == ERROR_CODE["server.order.courseNotPaid"]
    tree.assert_called_once_with(app, "course", "learner", preview)
    assert permission.call_count == int(preview)


def test_live_access_rejects_absent_lesson_and_stops_at_denied_preview_permission(
    monkeypatch: object,
) -> None:
    app = Flask(__name__)
    tree = Mock(
        return_value=SimpleNamespace(
            outline_items=[SimpleNamespace(bid="other", children=[])]
        )
    )
    monkeypatch.setattr(live, "get_outline_item_tree", tree)
    args = {
        "shifu_bid": "course",
        "outline_bid": "lesson",
        "user_bid": "learner",
        "preview_mode": False,
    }
    with pytest.raises(AppError) as error:
        live._require_course_access(app, **args)
    assert error.value.code == ERROR_CODE["server.shifu.lessonNotFoundInCourse"]
    tree.reset_mock()
    monkeypatch.setattr(
        live,
        "require_shifu_preview_permission",
        Mock(side_effect=AppError("denied", 401)),
    )
    args["preview_mode"] = True
    with pytest.raises(AppError, match="denied"):
        live._require_course_access(app, **args)
    tree.assert_not_called()


@pytest.fixture
def live_config(monkeypatch: object) -> object:
    info = SimpleNamespace(
        ask_mode=1,
        ask_model=live.GEMINI_LIVE_MODEL_ID,
        ask_provider_config={"provider": "llm", "mode": "provider_only", "config": {}},
    )
    monkeypatch.setattr(live, "get_follow_up_info_v2", lambda *_: info)
    monkeypatch.setattr(
        live, "get_effective_ask_provider_config", lambda config: config
    )
    available = Mock(return_value=True)
    monkeypatch.setattr(live, "is_live_follow_up_model_available", available)
    return SimpleNamespace(info=info, available=available)


def _resolve_config() -> object:
    return live._resolve_live_config(
        Flask(__name__),
        shifu_bid="course",
        outline_bid="lesson",
        progress_record_bid="progress",
        preview_mode=False,
    )


@pytest.mark.parametrize("voice", [None, "Kore", "Aoede"])
def test_live_config_uses_valid_teacher_voice_or_default(
    live_config: object, voice: str | None
) -> None:
    if voice is not None:
        live_config.info.ask_provider_config["config"]["live_voice"] = voice
    info, resolved_voice = _resolve_config()
    assert info is live_config.info
    assert resolved_voice == (voice or live.DEFAULT_GEMINI_LIVE_VOICE)
    live_config.available.assert_called_once_with(live.GEMINI_LIVE_MODEL_ID)


@pytest.mark.parametrize(
    "invalid", ["disabled", "text-model", "unavailable", "voice", "provider", "mode"]
)
def test_live_config_rejects_unavailable_or_incompatible_settings(
    live_config: object, invalid: str
) -> None:
    if invalid == "disabled":
        live_config.info.ask_mode = ASK_MODE_DISABLE
    elif invalid == "text-model":
        live_config.info.ask_model = "text-model"
    elif invalid == "unavailable":
        live_config.available.return_value = False
    elif invalid == "voice":
        live_config.info.ask_provider_config["config"]["live_voice"] = (
            "unsupported-voice"
        )
    else:
        live_config.info.ask_provider_config[invalid] = "unsupported"
    expected = (
        live.LiveFollowUpModelUnavailableError if invalid == "unavailable" else AppError
    )
    with pytest.raises(expected):
        _resolve_config()
    if invalid in {"disabled", "text-model"}:
        live_config.available.assert_not_called()


def test_live_conversation_uses_voice_prompt_and_only_nonempty_dialogue_history(
    monkeypatch: object,
) -> None:
    app = Flask(__name__)
    user = object()
    follow_up = object()
    binding = SimpleNamespace(
        user_bid="user",
        shifu_bid="course",
        outline_bid="lesson",
        progress_record_bid="progress",
        language="fr-FR",
        anchor_element_bid="anchor",
    )
    monkeypatch.setattr(live, "load_user_aggregate", lambda _: user)
    monkeypatch.setattr(live, "load_prompt_template", lambda _: "Voice system prompt")
    builder = Mock(
        return_value=SimpleNamespace(
            system_instruction="Resolved instruction",
            llm_messages=[
                {"role": "system", "content": "Do not replay this"},
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
                {"role": "assistant", "content": " "},
                {"role": "tool", "content": "Internal"},
            ],
        )
    )
    monkeypatch.setattr(live, "build_follow_up_conversation_context", builder)
    prompt, history = live._build_conversation(
        app, binding=binding, follow_up_info=follow_up
    )
    assert prompt == "Resolved instruction"
    assert [(turn.role, turn.text) for turn in history] == [
        ("user", "Question"),
        ("assistant", "Answer"),
    ]
    assert builder.call_args.kwargs == {
        "user_info": user,
        "shifu_bid": "course",
        "outline_item_bid": "lesson",
        "progress_record_bid": "progress",
        "follow_up_info": follow_up,
        "course_system_prompt": None,
        "fallback_system_prompt": "Voice system prompt",
        "use_learner_language": False,
        "runtime_language": "fr-FR",
        "anchor_element_bid": "anchor",
        "max_history_messages": 20,
    }


def test_live_conversation_rejects_unavailable_learner_before_building_context(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(live, "load_user_aggregate", lambda _: None)
    builder = Mock()
    monkeypatch.setattr(live, "build_follow_up_conversation_context", builder)
    with pytest.raises(RuntimeError, match="Live user is unavailable"):
        live._build_conversation(
            Flask(__name__),
            binding=SimpleNamespace(user_bid="missing"),
            follow_up_info=object(),
        )
    builder.assert_not_called()


def test_first_publication_keeps_draft_voice_anchor_and_source(
    app: Flask, monkeypatch: pytest.MonkeyPatch, runtime_dependencies: object
) -> None:
    """Keep the draft voice context after publication and honor revocation."""
    from uuid import uuid4

    from flaskr.dao import db
    from flaskr.dao.uow import unit_of_work
    from flaskr.service.learn import utils_v2
    from flaskr.service.learn.agent.session_store import stage_lesson_attempt_source
    from flaskr.service.learn.gemini_live_token import GeminiLiveEphemeralToken
    from flaskr.service.learn.live_follow_up_admission import (
        AdmissionRequest,
        AdmissionResult,
    )
    from flaskr.service.learn.live_follow_up_capacity import LiveFollowUpCapacityLease
    from flaskr.service.learn.live_follow_up_session_store import (
        LiveFollowUpTurnReservation,
        _decode_session,
    )
    from flaskr.service.learn.models import LearnGeneratedElement
    from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
    from flaskr.service.shifu.models import AiCourseAuth, DraftShifu, PublishedShifu
    from flaskr.service.shifu.shifu_publish_funcs import publish_shifu_draft
    from flaskr.service.user.repository import create_user_entity
    from flaskr.service.user.utils import generate_token
    from flaskr.util.datetime import now_utc

    from tests.common.fixtures.model_factories import (
        make_generated_element,
        make_progress_record,
    )

    _ = runtime_dependencies
    course = published_course._seed_course(app, publish=False)
    learner_bid, anchor_bid, progress_bid = (uuid4().hex for _ in range(3))
    scope = {
        "shifu_bid": course.course_bid,
        "outline_bid": course.outline_bid,
        "user_bid": learner_bid,
    }

    def select_draft_model(shifu_info: object, *, follow_up: bool) -> str:
        assert isinstance(shifu_info, DraftShifu)
        assert follow_up
        return live.GEMINI_LIVE_MODEL_ID

    monkeypatch.setattr(utils_v2, "selection_model", select_draft_model)
    monkeypatch.setattr(live, "is_live_follow_up_model_available", lambda *_: True)

    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=learner_bid, identify=learner_bid, nickname="Learner"
            )
            permission = AiCourseAuth(
                course_id=course.course_bid,
                user_id=learner_bid,
                auth_type="view",
                status=1,
            )
            db.session.add(permission)
            token = generate_token(app, learner_bid)
            db.session.add(
                make_progress_record(
                    progress_record_bid=progress_bid,
                    user_bid=learner_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    status=LEARN_STATUS_IN_PROGRESS,
                )
            )
            db.session.add(
                make_generated_element(
                    element_bid=anchor_bid,
                    user_bid=learner_bid,
                    shifu_bid=course.course_bid,
                    outline_item_bid=course.outline_bid,
                    progress_record_bid=progress_bid,
                    element_type="text",
                    event_type="element",
                    content_text="A draft classroom example.",
                )
            )
        source = live.resolve_lesson_source(app, **scope, preview_mode=True)
        with unit_of_work():
            assert stage_lesson_attempt_source(**scope, source=source.source)
        assert not PublishedShifu.query.filter_by(shifu_bid=course.course_bid).count()

    issued_at_ms = int(now_utc().timestamp() * 1000)

    def begin_admission(
        _app: Flask, operation: AdmissionRequest, **_kw: object
    ) -> AdmissionResult:
        return AdmissionResult(
            data={
                "admission_revision": "test-revision",
                "request_bid": operation.request_bid,
            },
            lease=LiveFollowUpCapacityLease("test-lease", learner_bid, "test-worker"),
            issued_at_ms=issued_at_ms,
            deadline_ms=issued_at_ms + 15_000,
        )

    session_payloads = []
    monkeypatch.setattr(live, "is_gemini_live_enabled", lambda: True)
    monkeypatch.setattr(live, "is_gemini_live_rotation_enabled", lambda: False)
    monkeypatch.setattr(
        live,
        "get_config",
        lambda key, default=None: "test-key" if key == "GEMINI_API_KEY" else default,
    )
    monkeypatch.setattr(live, "begin_admission", begin_admission)
    monkeypatch.setattr(
        live,
        "mint_gemini_live_ephemeral_token",
        lambda *, current_time, **_kw: GeminiLiveEphemeralToken(
            token="auth_tokens/test",
            expires_at=current_time + timedelta(minutes=15),
            new_session_expires_at=current_time + timedelta(seconds=30),
        ),
    )
    monkeypatch.setattr(
        live,
        "complete_admission",
        lambda *_a, session_payload: session_payloads.append(session_payload) or True,
    )
    monkeypatch.setattr(live, "admission_time", lambda: issued_at_ms / 1000)

    origin = "https://learn.example.com"
    headers = {"Origin": origin, "Token": token}
    client = app.test_client()

    def post(path: str, payload: dict[str, object]) -> dict[str, object]:
        return client.post(
            path, json=payload, base_url=origin, headers=headers
        ).get_json()

    create_path = f"/api/learn/shifu/{course.course_bid}/live-follow-up/{course.outline_bid}/session"
    for index, preview_mode in enumerate((True, False), start=1):
        if not preview_mode:
            publish_shifu_draft(
                app, course.user_bid, course.course_bid, "", sync_summary=True
            )
        response = post(
            create_path,
            {
                "request_bid": f"01990000-0000-7000-8000-{index:012d}",
                "anchor_element_bid": anchor_bid,
                "preview_mode": preview_mode,
                "learning_mode": "read",
                "surface": "teacher_preview" if preview_mode else "read_content",
            },
        )
        assert response["code"] == 0
        data = response["data"]
        history = data["history"]["clientContent"]["turns"]
        assert [turn["parts"][0]["text"] for turn in history] == [
            "A draft classroom example."
        ]
        session_bid = data["session_bid"]
        stored = _decode_session(session_payloads.pop())
        assert stored.binding.session_bid == session_bid
        assert stored.binding.preview_mode is preview_mode
        assert stored.binding.source_is_draft is (not preview_mode)

    monkeypatch.setattr(live, "load_live_follow_up_session", lambda *_a, **_kw: stored)
    monkeypatch.setattr(live, "current_admission", lambda *_a, **_kw: True)
    monkeypatch.setattr(live, "touch_live_follow_up_session", Mock())
    monkeypatch.setattr(
        live, "live_follow_up_persistence_lock", lambda *_: nullcontext()
    )
    monkeypatch.setattr(
        live,
        "reserve_live_follow_up_turn",
        lambda _app, *, session_bid, turn_index, **_kw: LiveFollowUpTurnReservation(
            session_bid, turn_index, "test-claim"
        ),
    )
    monkeypatch.setattr(live, "commit_live_follow_up_turn_reservation", Mock())
    release = Mock()
    monkeypatch.setattr(live, "release_live_follow_up_turn_reservation", release)
    monkeypatch.setattr(live, "LiveFollowUpTrace", Mock(return_value=Mock(trace_id="")))

    session_path = f"/api/learn/live-follow-up/session/{session_bid}"
    assert post(f"{session_path}/heartbeat", {})["code"] == 0
    turn_report = {
        "user_transcript": "Question about the draft",
        "played_answer_transcript": "An answer about the draft",
        "interrupted": False,
    }
    accepted = post(f"{session_path}/turn", {**turn_report, "turn_index": 1})
    assert accepted["code"] == 0
    assert accepted["data"]["history_saved"] is True

    with app.app_context(), unit_of_work():
        AiCourseAuth.query.filter_by(
            course_id=course.course_bid, user_id=learner_bid
        ).one().status = 0

    heartbeat = post(f"{session_path}/heartbeat", {})
    assert heartbeat["code"] == ERROR_CODE["server.shifu.noPermission"]

    denied = post(f"{session_path}/turn", {**turn_report, "turn_index": 2})
    assert denied["code"] == ERROR_CODE["server.common.paramsError"]
    release.assert_called_once()
    with app.app_context():
        assert (
            LearnGeneratedElement.query.filter_by(
                progress_record_bid=progress_bid
            ).count()
            == 3
        )
