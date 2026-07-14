"""Tests for the /run SSE emitter extraction (B6 PR1).

Covers the delegation wiring between ``RunScriptContextV2`` wrappers and
``RunEventEmitter``, the preservation of instance-level override seams, and
a payload smoke for emitter-side event construction.
"""

import types
import unittest

from flask import Flask

import flaskr.dao as dao
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.context_v2 import RunScriptContextV2
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.learn.run import RunEventEmitter


def _make_context() -> RunScriptContextV2:
    # Bypass __init__ since we only need helper methods for these tests.
    ctx = RunScriptContextV2.__new__(RunScriptContextV2)
    ctx._stop_event = None
    return ctx


class _RecordingEmitter:
    """Stand-in emitter recording every delegated call."""

    def __init__(self):
        self.calls = []

    def render_outline_updates(self, outline_updates, new_chapter=False):
        self.calls.append(("render_outline_updates", outline_updates, new_chapter))
        yield "outline-event"

    def emit_next_chapter_interaction(self, progress_record):
        self.calls.append(("emit_next_chapter_interaction", progress_record))
        yield "next-event"

    def emit_lesson_feedback_interaction(self, progress_record):
        self.calls.append(("emit_lesson_feedback_interaction", progress_record))
        yield "feedback-event"

    def is_access_gate_blocking_interaction(self, parsed_interaction):
        self.calls.append(("is_access_gate_blocking_interaction", parsed_interaction))
        return True

    def maybe_emit_feedback_after_access_gate(
        self, *, parsed_interaction, progress_record, is_tail_gate
    ):
        self.calls.append(
            (
                "maybe_emit_feedback_after_access_gate",
                parsed_interaction,
                progress_record,
                is_tail_gate,
            )
        )
        yield "gate-feedback-event"

    def emit_feedback_after_exception_gate(self):
        self.calls.append(("emit_feedback_after_exception_gate",))
        yield "exception-feedback-event"

    def ensure_current_attend_for_gate_interaction(self):
        self.calls.append(("ensure_current_attend_for_gate_interaction",))
        return "attend"

    def emit_current_progress_gate_interaction(self, content):
        self.calls.append(("emit_current_progress_gate_interaction", content))
        yield "gate-interaction-event"

    def emit_completion_tail_interactions(
        self, *, progress_record, current_outline_completed, has_next_outline_item
    ):
        self.calls.append(
            (
                "emit_completion_tail_interactions",
                progress_record,
                current_outline_completed,
                has_next_outline_item,
            )
        )
        yield "tail-event"


class EmitterAccessorTests(unittest.TestCase):
    def test_lazy_creation_and_caching(self):
        ctx = _make_context()

        emitter = ctx._event_emitter

        self.assertIsInstance(emitter, RunEventEmitter)
        self.assertIs(emitter._context, ctx)
        self.assertIs(ctx._event_emitter, emitter)


class WrapperDelegationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = _make_context()
        self.emitter = _RecordingEmitter()
        self.ctx.__dict__["_run_event_emitter"] = self.emitter

    def test_render_outline_updates_delegates(self):
        updates = [object()]
        events = list(self.ctx._render_outline_updates(updates, new_chapter=True))
        self.assertEqual(events, ["outline-event"])
        self.assertEqual(
            self.emitter.calls, [("render_outline_updates", updates, True)]
        )

    def test_emit_next_chapter_interaction_delegates(self):
        progress = object()
        events = list(self.ctx._emit_next_chapter_interaction(progress))
        self.assertEqual(events, ["next-event"])
        self.assertEqual(
            self.emitter.calls, [("emit_next_chapter_interaction", progress)]
        )

    def test_emit_lesson_feedback_interaction_delegates(self):
        progress = object()
        events = list(self.ctx._emit_lesson_feedback_interaction(progress))
        self.assertEqual(events, ["feedback-event"])
        self.assertEqual(
            self.emitter.calls, [("emit_lesson_feedback_interaction", progress)]
        )

    def test_is_access_gate_blocking_interaction_delegates(self):
        parsed = {"buttons": []}
        self.assertTrue(self.ctx._is_access_gate_blocking_interaction(parsed))
        self.assertEqual(
            self.emitter.calls, [("is_access_gate_blocking_interaction", parsed)]
        )

    def test_maybe_emit_feedback_after_access_gate_delegates(self):
        parsed = {"buttons": []}
        progress = object()
        events = list(
            self.ctx._maybe_emit_feedback_after_access_gate(
                parsed_interaction=parsed,
                progress_record=progress,
                is_tail_gate=True,
            )
        )
        self.assertEqual(events, ["gate-feedback-event"])
        self.assertEqual(
            self.emitter.calls,
            [("maybe_emit_feedback_after_access_gate", parsed, progress, True)],
        )

    def test_emit_feedback_after_exception_gate_delegates(self):
        events = list(self.ctx._emit_feedback_after_exception_gate())
        self.assertEqual(events, ["exception-feedback-event"])
        self.assertEqual(self.emitter.calls, [("emit_feedback_after_exception_gate",)])

    def test_ensure_current_attend_for_gate_interaction_delegates(self):
        self.assertEqual(
            self.ctx._ensure_current_attend_for_gate_interaction(), "attend"
        )
        self.assertEqual(
            self.emitter.calls, [("ensure_current_attend_for_gate_interaction",)]
        )

    def test_emit_current_progress_gate_interaction_delegates(self):
        events = list(self.ctx._emit_current_progress_gate_interaction("content"))
        self.assertEqual(events, ["gate-interaction-event"])
        self.assertEqual(
            self.emitter.calls,
            [("emit_current_progress_gate_interaction", "content")],
        )

    def test_emit_completion_tail_interactions_delegates(self):
        progress = object()
        events = list(
            self.ctx._emit_completion_tail_interactions(
                progress_record=progress,
                current_outline_completed=True,
                has_next_outline_item=False,
            )
        )
        self.assertEqual(events, ["tail-event"])
        self.assertEqual(
            self.emitter.calls,
            [("emit_completion_tail_interactions", progress, True, False)],
        )


class EmitterContextSeamTests(unittest.TestCase):
    """The emitter must dispatch cross-calls through the context wrappers so
    instance-level overrides on the context keep taking effect."""

    def test_completion_tail_uses_context_overrides(self):
        ctx = _make_context()
        calls: list[str] = []

        def _emit_feedback(_progress):
            calls.append("feedback")
            yield "feedback-event"

        def _emit_next(_progress):
            calls.append("next")
            yield "next-event"

        ctx._emit_lesson_feedback_interaction = _emit_feedback
        ctx._emit_next_chapter_interaction = _emit_next

        events = list(
            ctx._event_emitter.emit_completion_tail_interactions(
                progress_record=object(),
                current_outline_completed=True,
                has_next_outline_item=True,
            )
        )

        self.assertEqual(calls, ["next", "feedback"])
        self.assertEqual(events, ["next-event", "feedback-event"])

    def test_access_gate_feedback_uses_context_overrides(self):
        ctx = _make_context()
        calls: list[str] = []

        def _emit_feedback(_progress):
            calls.append("feedback")
            yield "feedback-event"

        ctx._is_access_gate_blocking_interaction = lambda _parsed: True
        ctx._emit_lesson_feedback_interaction = _emit_feedback

        events = list(
            ctx._event_emitter.maybe_emit_feedback_after_access_gate(
                parsed_interaction={"buttons": [{"value": "_sys_pay"}]},
                progress_record=object(),
                is_tail_gate=True,
            )
        )

        self.assertEqual(calls, ["feedback"])
        self.assertEqual(events, ["feedback-event"])


class EmitterPayloadSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("run-emitter-payload-tests")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)
        with cls.app.app_context():
            dao.db.create_all()

    def setUp(self):
        self.app = self.__class__.app
        self.ctx = _make_context()
        self.ctx.app = self.app
        self.ctx._outline_item_info = types.SimpleNamespace(bid="outline-1")
        self.ctx._current_attend = types.SimpleNamespace(
            progress_record_bid="progress-1",
            outline_item_bid="outline-1",
            shifu_bid="shifu-1",
            block_position=2,
        )
        self.ctx._user_info = types.SimpleNamespace(user_id="user-1")
        with self.app.app_context():
            LearnGeneratedBlock.query.delete()
            dao.db.session.commit()

    def test_next_chapter_payload_constructed_by_emitter(self):
        with self.app.app_context():
            events = list(
                self.ctx._event_emitter.emit_next_chapter_interaction(
                    self.ctx._current_attend
                )
            )

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.type, GeneratedType.INTERACTION)
            self.assertEqual(event.outline_bid, "outline-1")
            self.assertIn(CONTEXT_INTERACTION_NEXT, event.content)

            stored_blocks = LearnGeneratedBlock.query.filter(
                LearnGeneratedBlock.progress_record_bid == "progress-1"
            ).all()
            self.assertEqual(len(stored_blocks), 1)
            self.assertEqual(
                stored_blocks[0].generated_block_bid, event.generated_block_bid
            )


if __name__ == "__main__":
    unittest.main()
