"""Verify reactions and generated-content lookups obey learner and course scope."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import ERROR_CODE, AppError
from flaskr.service.learn import learn_funcs as learn
from flaskr.service.learn.context_v2 import RunScriptPreviewContextV2
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.shifu.consts import UNIT_TYPE_VALUE_TRIAL
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.tts.validation import StrictTTSSettings


@pytest.fixture
def stored(app: object) -> object:
    identity = uuid.uuid4().hex
    with app.app_context(), unit_of_work():
        db.session.add(
            LearnGeneratedBlock(
                generated_block_bid=identity,
                shifu_bid=identity,
                user_bid=identity,
                outline_item_bid=identity,
                generated_content="Lesson content",
                position=4,
                status=1,
                deleted=0,
                liked=0,
            )
        )
        db.session.add(
            DraftOutlineItem(
                shifu_bid=identity,
                outline_item_bid=identity,
                title="Draft lesson",
                type=UNIT_TYPE_VALUE_TRIAL,
                position=0,
                deleted=0,
            )
        )
        db.session.add(
            PublishedOutlineItem(
                shifu_bid=identity,
                outline_item_bid=identity,
                title="Published lesson",
                type=UNIT_TYPE_VALUE_TRIAL,
                position=0,
                deleted=0,
            )
        )
    yield identity
    with app.app_context(), unit_of_work():
        for model in (
            LearnGeneratedBlock,
            DraftOutlineItem,
            PublishedOutlineItem,
            DraftShifu,
            PublishedShifu,
        ):
            model.query.filter_by(shifu_bid=identity).delete()


@pytest.mark.parametrize(
    ("action", "liked"), [("like", 1), ("dislike", -1), ("none", 0)]
)
def test_reaction_persists_on_the_owned_active_block(
    app: object, stored: str, action: str, liked: int
) -> None:
    assert learn.handle_reaction(app, stored, stored, stored, action) is True
    with app.app_context():
        assert (
            LearnGeneratedBlock.query.filter_by(generated_block_bid=stored).one().liked
            == liked
        )


@pytest.mark.parametrize("scope", ["user", "course", "deleted", "inactive", "missing"])
def test_reaction_cannot_modify_an_inaccessible_block(
    app: object, stored: str, scope: str
) -> None:
    user = "other-user" if scope == "user" else stored
    course = "other-course" if scope == "course" else stored
    block = "absent" if scope == "missing" else stored
    if scope in {"deleted", "inactive"}:
        with app.app_context(), unit_of_work():
            row = LearnGeneratedBlock.query.filter_by(generated_block_bid=stored).one()
            if scope == "deleted":
                row.deleted = 1
            else:
                row.status = 0
    with pytest.raises(AppError):
        learn.handle_reaction(app, course, user, block, "like")
    with app.app_context():
        assert (
            LearnGeneratedBlock.query.filter_by(generated_block_bid=stored).one().liked
            == 0
        )


def test_invalid_reaction_does_not_change_existing_preference(
    app: object, stored: str
) -> None:
    learn.handle_reaction(app, stored, stored, stored, "like")
    with pytest.raises(AppError):
        learn.handle_reaction(app, stored, stored, stored, "invalid")
    with app.app_context():
        assert (
            LearnGeneratedBlock.query.filter_by(generated_block_bid=stored).one().liked
            == 1
        )


@pytest.mark.parametrize("preview", [True, False])
def test_generated_content_resolves_matching_draft_or_published_lesson(
    app: object, stored: str, preview: bool
) -> None:
    result = learn.get_generated_content(
        app, stored, stored, stored, preview_mode=preview
    )
    assert result.position == 4
    assert result.outline_name == ("Draft lesson" if preview else "Published lesson")
    assert result.is_trial_lesson is True


def test_generated_content_returns_empty_for_another_learner(
    app: object, stored: str
) -> None:
    result = learn.get_generated_content(
        app, stored, stored, "other-user", preview_mode=False
    )
    assert result.position == 0
    assert result.outline_name == ""
    assert result.is_trial_lesson is False


def test_generated_content_preserves_position_when_outline_was_removed(
    app: object, stored: str
) -> None:
    with app.app_context(), unit_of_work():
        PublishedOutlineItem.query.filter_by(shifu_bid=stored).delete()
    result = learn.get_generated_content(
        app, stored, stored, stored, preview_mode=False
    )
    assert result.position == 4
    assert result.outline_name == ""
    assert result.is_trial_lesson is False


@pytest.mark.parametrize("has_draft", [True, False])
def test_preview_record_lookup_prefers_draft_and_falls_back_to_published(
    app: object, stored: str, has_draft: bool
) -> None:
    with app.app_context():
        with unit_of_work():
            db.session.add(
                PublishedShifu(shifu_bid=stored, title="Published", deleted=0)
            )
            if has_draft:
                db.session.add(DraftShifu(shifu_bid=stored, title="Draft", deleted=0))
            else:
                DraftOutlineItem.query.filter_by(shifu_bid=stored).delete()
        preview = RunScriptPreviewContextV2(app)
        outline = preview._get_outline_record(stored, stored)
        assert outline.title == ("Draft lesson" if has_draft else "Published lesson")
        assert preview._get_shifu_record(stored, has_draft_outline=True).title == (
            "Draft" if has_draft else "Published"
        )
        assert (
            preview._get_shifu_record(stored, has_draft_outline=False).title
            == "Published"
        )


@pytest.mark.parametrize("preview", [True, False])
def test_course_tts_settings_validate_and_resolve_runtime_voice(
    app: object, stored: str, preview: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = DraftShifu if preview else PublishedShifu
    with app.app_context(), unit_of_work():
        db.session.add(
            model(
                shifu_bid=stored,
                tts_enabled=1,
                tts_provider=" MINIMAX ",
                tts_model=" model ",
                tts_voice_id=" voice ",
                tts_speed=1.25,
                tts_pitch=2,
                tts_emotion=" happy ",
                deleted=0,
            )
        )
    validated = StrictTTSSettings("minimax", "model", "voice", 1.25, 2, "happy")
    validate = Mock(return_value=validated)
    voice = SimpleNamespace()
    audio = SimpleNamespace()
    monkeypatch.setattr(learn, "validate_tts_settings_strict", validate)
    resolve = Mock(return_value="ready-voice")
    monkeypatch.setattr(learn, "_resolve_runtime_tts_voice_id", resolve)
    monkeypatch.setattr(learn, "get_default_voice_settings", lambda _provider: voice)
    monkeypatch.setattr(learn, "get_default_audio_settings", lambda _provider: audio)
    with app.app_context():
        assert learn._resolve_shifu_tts_settings(
            app, shifu_bid=stored, preview_mode=preview
        ) == ("minimax", "model", voice, audio)
    validate.assert_called_once_with(
        provider="minimax",
        model="model",
        voice_id="voice",
        speed=Decimal("1.25"),
        pitch=2,
        emotion="happy",
    )
    resolve.assert_called_once_with(app, "minimax", "voice", shifu_bid=stored)
    assert vars(voice) == {
        "voice_id": "ready-voice",
        "speed": 1.25,
        "pitch": 2,
        "emotion": "happy",
    }


@pytest.mark.parametrize("existing", [True, False])
def test_course_tts_rejects_missing_or_disabled_course(
    app: object, stored: str, existing: bool
) -> None:
    if existing:
        with app.app_context(), unit_of_work():
            db.session.add(PublishedShifu(shifu_bid=stored, tts_enabled=0, deleted=0))
    with app.app_context(), pytest.raises(AppError) as raised:
        learn._resolve_shifu_tts_settings(app, shifu_bid=stored, preview_mode=False)
    assert (
        raised.value.code
        == ERROR_CODE[
            "server.shifu.ttsNotEnabled" if existing else "server.shifu.shifuNotFound"
        ]
    )
