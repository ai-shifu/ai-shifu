"""A guest who signs in mid-course keeps the lesson state the merge carries over.

Besides progress records and generated blocks, the phone/email merge moves the MDF 2.0 agent
session, the elements and audio hanging off migrated blocks, and the guest's live course memory.
"""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.service.learn.agent import session_store
from flaskr.service.learn.agent.models import LearnAgentSession, active_key_for
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnGeneratedElement,
    LearnProgressRecord,
)
from flaskr.service.memory.api import delete_course_memory, load_memory
from flaskr.service.memory.course_memory import course_memory_deletion_state
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.profile.models import VariableValue
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT_VALUE
from flaskr.service.tts.models import LearnGeneratedAudio
from flaskr.service.user.phone_flow import migrate_user_study_record
from markdownflow.engine import ScriptBundle, Session

from tests.common.fixtures.model_factories import (
    make_generated_block,
    make_generated_element,
    make_progress_record,
)

GUEST = "guest-merge-user"
TARGET = "target-merge-user"
COURSE = "course-merge"
OTHER_COURSE = "course-merge-other"


@pytest.fixture(autouse=True)
def _clean(app: object):  # noqa: ANN202 - pytest fixture
    def wipe() -> None:
        for model in (
            LearnAgentSession,
            LearnGeneratedAudio,
            LearnGeneratedElement,
            LearnGeneratedBlock,
            LearnProgressRecord,
        ):
            model.query.delete()
        VariableValue.query.filter(VariableValue.user_bid.in_([GUEST, TARGET])).delete(
            synchronize_session=False
        )
        db.session.commit()

    with app.app_context():
        wipe()
        yield
        wipe()


@pytest.fixture(autouse=True)
def _no_profile_definitions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "flaskr.service.memory.course_values.get_profile_item_definition_list",
        lambda *_args, **_kwargs: [],
    )


def _add_progress(user_bid: str, shifu_bid: str, outline: str) -> None:
    progress_bid = f"progress-{user_bid}-{outline}"
    block_bid = f"block-{user_bid}-{outline}"
    db.session.add(
        make_progress_record(
            progress_record_bid=progress_bid,
            shifu_bid=shifu_bid,
            outline_item_bid=outline,
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
        )
    )
    db.session.add(
        make_generated_block(
            generated_block_bid=block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            block_bid=f"source-{outline}",
            outline_item_bid=outline,
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_CONTENT_VALUE,
            generated_content="hello",
            position=1,
            status=1,
        )
    )
    db.session.add(
        make_generated_element(
            element_bid=f"element-{user_bid}-{outline}",
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            generated_block_bid=block_bid,
            outline_item_bid=outline,
            shifu_bid=shifu_bid,
        )
    )
    db.session.add(
        LearnGeneratedAudio(
            audio_bid=f"audio-{user_bid}-{outline}",
            generated_block_bid=block_bid,
            progress_record_bid=progress_bid,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
        )
    )
    db.session.commit()


def _save_session(
    app: object,
    user_bid: str,
    shifu_bid: str,
    outline: str,
    *,
    preview_mode: bool = False,
    script: str = "Teach the lesson.",
) -> None:
    session = Session(script=ScriptBundle(script=script), user_id=user_bid)
    session.turn = 2
    session_store.save_agent_session(
        app,
        session,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_item_bid=outline,
        preview_mode=preview_mode,
    )


def _add_value(
    user_bid: str, shifu_bid: str, key: str, value: str, *, deleted: int = 0
) -> VariableValue:
    row = VariableValue(
        variable_value_bid=f"{user_bid[:8]}{key}{value}"[:32],
        variable_bid="",
        shifu_bid=shifu_bid,
        user_bid=user_bid,
        key=key,
        value=value,
        deleted=deleted,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _merge(app: object) -> None:
    migrate_user_study_record(app, GUEST, TARGET, COURSE)
    db.session.commit()


def test_merge_moves_the_live_agent_session_to_the_target(app: object) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _save_session(app, GUEST, COURSE, "outline-1", script="Guest lesson.")
        _save_session(app, GUEST, COURSE, "outline-1", preview_mode=True)
        _add_progress(GUEST, OTHER_COURSE, "outline-other")
        _save_session(app, GUEST, OTHER_COURSE, "outline-other")

        _merge(app)

        moved = session_store.load_agent_session(app, TARGET, "outline-1")
        assert moved is not None
        assert moved.script.script == "Guest lesson."
        assert session_store.load_agent_session(app, GUEST, "outline-1") is None

        # The preview scope is an author's draft conversation, never a learner's lesson.
        preview = LearnAgentSession.query.filter_by(
            active_key=active_key_for(GUEST, "outline-1", preview_mode=True)
        ).one()
        assert preview.user_bid == GUEST
        assert (
            session_store.load_agent_session(
                app, TARGET, "outline-1", preview_mode=True
            )
            is None
        )

        other = LearnAgentSession.query.filter_by(shifu_bid=OTHER_COURSE).one()
        assert other.user_bid == GUEST
        assert other.active_key == active_key_for(GUEST, "outline-other")


def test_merge_keeps_the_target_session_for_outlines_it_already_started(
    app: object,
) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _save_session(app, GUEST, COURSE, "outline-1", script="Guest lesson.")
        _add_progress(TARGET, COURSE, "outline-1")
        _save_session(app, TARGET, COURSE, "outline-1", script="Target lesson.")

        _merge(app)

        kept = session_store.load_agent_session(app, TARGET, "outline-1")
        assert kept is not None
        assert kept.script.script == "Target lesson."
        guest = session_store.load_agent_session(app, GUEST, "outline-1")
        assert guest is not None
        assert guest.script.script == "Guest lesson."


def test_merge_moves_elements_and_audio_of_migrated_blocks(app: object) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _add_progress(GUEST, OTHER_COURSE, "outline-other")

        _merge(app)

        element = LearnGeneratedElement.query.filter_by(
            element_bid=f"element-{GUEST}-outline-1"
        ).one()
        audio = LearnGeneratedAudio.query.filter_by(
            audio_bid=f"audio-{GUEST}-outline-1"
        ).one()
        assert element.user_bid == TARGET
        assert audio.user_bid == TARGET

        other_element = LearnGeneratedElement.query.filter_by(
            element_bid=f"element-{GUEST}-outline-other"
        ).one()
        other_audio = LearnGeneratedAudio.query.filter_by(
            audio_bid=f"audio-{GUEST}-outline-other"
        ).one()
        assert other_element.user_bid == GUEST
        assert other_audio.user_bid == GUEST


def test_merge_leaves_other_courses_rows_that_share_a_progress_link(
    app: object,
) -> None:
    """Legacy rows can reuse a progress record identifier across courses."""
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        shared = f"progress-{GUEST}-outline-1"
        db.session.add(
            make_generated_block(
                generated_block_bid="other-block",
                progress_record_bid=shared,
                user_bid=GUEST,
                block_bid="source-other",
                outline_item_bid="outline-other",
                shifu_bid=OTHER_COURSE,
                type=BLOCK_TYPE_CONTENT_VALUE,
                generated_content="other",
                position=1,
                status=1,
            )
        )
        db.session.add(
            make_generated_element(
                element_bid="other-element",
                progress_record_bid=shared,
                user_bid=GUEST,
                generated_block_bid="other-block",
                outline_item_bid="outline-other",
                shifu_bid=OTHER_COURSE,
            )
        )
        db.session.add(
            LearnGeneratedAudio(
                audio_bid="other-audio",
                generated_block_bid="other-block",
                progress_record_bid=shared,
                user_bid=GUEST,
                shifu_bid=OTHER_COURSE,
            )
        )
        db.session.commit()

        _merge(app)

        assert (
            LearnGeneratedBlock.query.filter_by(generated_block_bid="other-block")
            .one()
            .user_bid
            == GUEST
        )
        assert (
            LearnGeneratedElement.query.filter_by(element_bid="other-element")
            .one()
            .user_bid
            == GUEST
        )
        assert (
            LearnGeneratedAudio.query.filter_by(audio_bid="other-audio").one().user_bid
            == GUEST
        )
        assert (
            LearnGeneratedElement.query.filter_by(
                element_bid=f"element-{GUEST}-outline-1"
            )
            .one()
            .user_bid
            == TARGET
        )


def test_merge_carries_guest_course_memory_without_overwriting_target(
    app: object,
) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _add_value(GUEST, COURSE, "goal", "old guest goal")
        _add_value(GUEST, COURSE, "goal", "guest goal")
        _add_value(GUEST, COURSE, "pet", "guest pet")
        _add_value(TARGET, COURSE, "pet", "target pet")
        _add_value(GUEST, COURSE, "share:answer", "reference payload")
        _add_value(GUEST, OTHER_COURSE, "city", "other course city")
        _add_value(GUEST, "", "hobby", "global hobby")

        _merge(app)

        variables = load_memory(
            app, TARGET, COURSE, include_course_variables=True
        ).variables
        assert variables["goal"] == "guest goal"
        assert variables["pet"] == "target pet"
        assert "city" not in variables
        assert "hobby" not in variables
        # The whole "goal" history moved: no older guest version is left to resurface.
        assert (
            VariableValue.query.filter_by(
                user_bid=GUEST, shifu_bid=COURSE, key="goal"
            ).count()
            == 0
        )
        assert (
            VariableValue.query.filter_by(
                user_bid=TARGET, shifu_bid=COURSE, key="goal"
            ).count()
            == 2
        )
        # A key the account already had stays the account's; the guest's row stays put.
        assert (
            VariableValue.query.filter_by(
                user_bid=GUEST, shifu_bid=COURSE, key="pet"
            ).count()
            == 1
        )

        assert (
            VariableValue.query.filter_by(
                user_bid=TARGET, key="share:answer", deleted=0
            ).count()
            == 0
        )
        assert (
            VariableValue.query.filter_by(user_bid=TARGET, shifu_bid=OTHER_COURSE)
            .filter(VariableValue.deleted == 0)
            .count()
            == 0
        )
        assert VariableValue.query.filter_by(user_bid=TARGET, shifu_bid="").count() == 0


def test_merge_does_not_resurrect_a_value_the_guest_deleted(app: object) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        forgotten = _add_value(GUEST, COURSE, "secret", "guest secret")
        delete_course_memory(GUEST, COURSE, forgotten.id)
        db.session.commit()
        _add_value(TARGET, COURSE, "mood", "target mood")
        _add_value(GUEST, COURSE, "mood", "guest mood")
        delete_course_memory(
            GUEST,
            COURSE,
            VariableValue.query.filter_by(user_bid=GUEST, key="mood", deleted=0)
            .one()
            .id,
        )
        db.session.commit()

        guest_generations, _ = course_memory_deletion_state(GUEST, COURSE)

        _merge(app)

        variables = load_memory(
            app, TARGET, COURSE, include_course_variables=True
        ).variables
        assert "secret" not in variables
        # A guest tombstone never hides the account's own value.
        assert variables["mood"] == "target mood"
        # The deletion moved with the value, under the same generation the migrated
        # session recorded, so a resumed lesson still drops the forgotten answer.
        generations, deleted = course_memory_deletion_state(TARGET, COURSE)
        assert "secret" in deleted
        assert generations["secret"] == guest_generations["secret"]


def test_merge_keeps_every_key_the_account_has_history_for(
    app: object,
) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _add_value(GUEST, COURSE, "older", "guest older")
        target_row = _add_value(TARGET, COURSE, "older", "target older")
        delete_course_memory(TARGET, COURSE, target_row.id)
        target_row = _add_value(TARGET, COURSE, "newer", "target newer")
        delete_course_memory(TARGET, COURSE, target_row.id)
        db.session.commit()
        _add_value(GUEST, COURSE, "newer", "guest newer")
        before = course_memory_deletion_state(TARGET, COURSE)

        _merge(app)

        variables = load_memory(
            app, TARGET, COURSE, include_course_variables=True
        ).variables
        # The account deleted both keys: its history wins, whichever side wrote last,
        # so a migrated session realigns to the same deletions on its next turn.
        assert "older" not in variables
        assert "newer" not in variables
        assert course_memory_deletion_state(TARGET, COURSE) == before


def test_merge_moves_course_memory_even_when_no_progress_moves(app: object) -> None:
    with app.app_context():
        _add_progress(GUEST, COURSE, "outline-1")
        _add_progress(TARGET, COURSE, "outline-1")
        _add_value(GUEST, COURSE, "goal", "guest goal")

        _merge(app)

        variables = load_memory(
            app, TARGET, COURSE, include_course_variables=True
        ).variables
        assert variables["goal"] == "guest goal"
