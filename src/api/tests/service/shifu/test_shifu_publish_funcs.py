"""Verify shifu publish funcs behavior."""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from flaskr.dao import db
from flaskr.service.common.models import AppError
from flaskr.service.learn.live_follow_up_config import GEMINI_LIVE_MODEL_ID
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)


def test_publish_shifu_draft_preserves_outline_updated_at(
    app: object, monkeypatch: object
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    original_load_existing_outline_items = module.load_existing_outline_items
    outline_load_calls = []

    def _record_outline_load(*args: object, **kwargs: object) -> object:
        outline_load_calls.append((args, kwargs))
        return original_load_existing_outline_items(*args, **kwargs)

    monkeypatch.setattr(
        module,
        "load_existing_outline_items",
        _record_outline_load,
    )

    draft_updated_at = datetime(2026, 6, 30, 10, 0, 0)
    with app.app_context():
        draft = DraftShifu(
            shifu_bid="publish-preserve-outline-updated-at",
            title="Draft",
            description="Desc",
            keywords="a,b",
            tts_enabled=1,
            default_listen_mode_enabled=1,
        )
        outline = DraftOutlineItem(
            outline_item_bid="publish-preserve-outline-lesson",
            shifu_bid="publish-preserve-outline-updated-at",
            title="Lesson",
            position="1",
            type=401,
            hidden=0,
            content="# Lesson",
            updated_at=draft_updated_at,
        )
        db.session.add_all([draft, outline])
        db.session.commit()

    module.publish_shifu_draft(
        app,
        user_id="user-1",
        shifu_id="publish-preserve-outline-updated-at",
        base_url="https://example.com",
    )

    with app.app_context():
        published_outline = (
            PublishedOutlineItem.query.filter_by(
                shifu_bid="publish-preserve-outline-updated-at",
                outline_item_bid="publish-preserve-outline-lesson",
                deleted=0,
            )
            .order_by(PublishedOutlineItem.id.desc())
            .first()
        )
        published_shifu = (
            PublishedShifu.query.filter_by(
                shifu_bid="publish-preserve-outline-updated-at",
                deleted=0,
            )
            .order_by(PublishedShifu.id.desc())
            .first()
        )

    assert published_outline is not None
    assert published_outline.updated_at == draft_updated_at
    assert published_shifu is not None
    assert published_shifu.default_listen_mode_enabled == 1
    assert outline_load_calls == [
        (("publish-preserve-outline-updated-at",), {"include_content": True})
    ]


def test_publish_rejects_invalid_live_contract_before_retiring_current_version(
    app: object,
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    shifu_bid = "publish-reject-invalid-live-contract"
    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title="Invalid Live draft",
                    llm="gpt-main",
                    ask_llm=GEMINI_LIVE_MODEL_ID,
                    ask_provider_config=json.dumps(
                        {
                            "provider": "dify",
                            "mode": "provider_only",
                            "config": {"live_voice": "Kore"},
                        }
                    ),
                ),
                PublishedShifu(
                    shifu_bid=shifu_bid,
                    title="Current published course",
                    llm="gpt-main",
                    deleted=0,
                ),
            ]
        )
        db.session.commit()

    with pytest.raises(AppError):
        module.publish_shifu_draft(
            app,
            user_id="teacher-1",
            shifu_id=shifu_bid,
            base_url="https://example.com",
        )

    with app.app_context():
        current = PublishedShifu.query.filter_by(
            shifu_bid=shifu_bid,
            deleted=0,
        ).one()
        assert current.title == "Current published course"


def test_publish_live_follow_up_defaults_official_voice(
    app: object,
) -> None:
    from flaskr.service.shifu import shifu_publish_funcs as module

    shifu_bid = "publish-live-default-voice"
    with app.app_context():
        db.session.add_all(
            [
                DraftShifu(
                    shifu_bid=shifu_bid,
                    title="Valid Live draft",
                    llm="gpt-main",
                    llm_temperature=Decimal("0.4"),
                    ask_llm=GEMINI_LIVE_MODEL_ID,
                    ask_provider_config="{}",
                ),
                DraftOutlineItem(
                    outline_item_bid="publish-live-default-voice-lesson",
                    shifu_bid=shifu_bid,
                    title="Lesson",
                    position="1",
                    type=401,
                    hidden=0,
                    content="# Lesson",
                ),
            ]
        )
        db.session.commit()

    module.publish_shifu_draft(
        app,
        user_id="teacher-1",
        shifu_id=shifu_bid,
        base_url="https://example.com",
    )

    with app.app_context():
        published = PublishedShifu.query.filter_by(
            shifu_bid=shifu_bid,
            deleted=0,
        ).one()
        assert json.loads(published.ask_provider_config) == {
            "provider": "llm",
            "mode": "provider_only",
            "config": {"live_voice": "Kore"},
        }


def test_publish_carries_the_flow_engine_setting_to_the_published_row(
    app: object,
) -> None:
    """Learners run the published row, so an author switching runtime must see it take effect.

    Without the copy the setting would sit in the draft looking correct while every learner kept
    getting the old runtime, which is the kind of failure nobody reports as a bug.
    """
    from flaskr.service.shifu import shifu_publish_funcs as module
    from flaskr.service.shifu.consts import FLOW_ENGINE_V2

    bid = "publish-carries-flow-engine"

    with app.app_context():
        draft = DraftShifu(
            shifu_bid=bid,
            title="Draft",
            description="Desc",
            keywords="a",
            flow_engine=FLOW_ENGINE_V2,
        )
        outline = DraftOutlineItem(
            outline_item_bid=f"{bid}-lesson",
            shifu_bid=bid,
            title="Lesson",
            position="1",
            type=401,
            hidden=0,
            content="# Lesson",
        )
        db.session.add_all([draft, outline])
        db.session.commit()

    module.publish_shifu_draft(
        app,
        user_id="user-1",
        shifu_id=bid,
        base_url="https://example.com",
    )

    with app.app_context():
        published = (
            PublishedShifu.query.filter_by(shifu_bid=bid)
            .order_by(PublishedShifu.id.desc())
            .first()
        )
        assert published is not None
        assert published.flow_engine == FLOW_ENGINE_V2


@pytest.mark.parametrize("ask_status", [5102, 5103])
def test_publish_preserves_every_course_owned_model_setting(
    app: object, monkeypatch: pytest.MonkeyPatch, ask_status: int
) -> None:
    from unittest.mock import Mock

    from flaskr.api import llm
    from flaskr.service.shifu import shifu_publish_funcs as module

    invoke = Mock(side_effect=AssertionError("Publishing must not regenerate prompts"))
    monkeypatch.setattr(llm, "invoke_llm", invoke)
    shifu_bid = f"course-only-settings-{ask_status}"
    settings = {
        "llm": "course-main",
        "llm_temperature": Decimal("0.7"),
        "llm_system_prompt": "Course teaching rules",
        "ask_enabled_status": ask_status,
        "ask_llm": "course-follow-up",
        "ask_llm_temperature": Decimal("0.2"),
        "ask_llm_system_prompt": "Course follow-up rules",
    }
    with app.app_context():
        db.session.add(DraftShifu(shifu_bid=shifu_bid, **settings))
        db.session.add(
            DraftOutlineItem(
                shifu_bid=shifu_bid,
                outline_item_bid=f"lesson-{ask_status}",
                title="Lesson",
                position="01",
                type=401,
                content="Lesson content",
            )
        )
        db.session.commit()
    module.publish_shifu_draft(app, "teacher-1", shifu_bid, "https://example.com")
    with app.app_context():
        course = PublishedShifu.query.filter_by(shifu_bid=shifu_bid).one()
        assert {key: getattr(course, key) for key in settings} == settings
        outline = PublishedOutlineItem.query.filter_by(shifu_bid=shifu_bid).one()
        assert outline.content == "Lesson content"
        assert all(not hasattr(outline, key) for key in settings)
    invoke.assert_not_called()
