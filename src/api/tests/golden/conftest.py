"""Shared fixtures for the golden recording harness.

This package records byte-level (post-normalization) fixtures of the ``/run``
SSE stream and key JSON endpoints so later refactors can prove the frontend
contract is unchanged (backend overhaul master plan, Phase 0).

Determinism strategy:

- A deterministic fake LLM is patched both on ``flaskr.api.llm`` and on the
  names imported directly into ``flaskr.service.learn.context_v2``,
  ``flaskr.service.learn.check_text`` and
  ``flaskr.service.learn.handle_input_ask`` (the session-level autouse fake in
  ``tests/conftest.py`` only patches ``flaskr.api.llm`` attributes, which the
  /run path bypasses via ``from flaskr.api.llm import chat_llm``).
- The fake LLM echoes JSON-looking user messages verbatim (markdown-flow uses
  the LLM to "translate" interaction button labels; echoing keeps interaction
  content byte-identical to the authored MarkdownFlow) and otherwise streams a
  fixed multi-token completion.
- SSE heartbeats are disabled (``SSE_HEARTBEAT_INTERVAL = 0``) because their
  count depends on wall-clock timing.
- Langfuse is already a no-op ``MockClient`` in tests (no LANGFUSE_* config).
- Redis is the process-local FakeRedis from ``tests/conftest.py``; it lacks
  ``eval`` so the ask semaphore fails open deterministically.
- Each scenario uses its own learner ``user_bid`` so progress state never
  leaks between scenarios or depends on test ordering.

Update mode: run with ``UPDATE_GOLDEN=1`` to rewrite fixture files instead of
asserting against them.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.common.fixtures.fake_llm import FakeLLMResponse

GOLDEN_DIR = Path(__file__).parent
FIXTURES_DIR = GOLDEN_DIR / "fixtures"

GOLDEN_SHIFU_BID = "golden-shifu-0001"
GOLDEN_CHAPTER_BID = "golden-chapter-0001"
GOLDEN_LESSON_BID = "golden-lesson-0001"
GOLDEN_CREATOR_BID = "golden-creator-0001"

# MarkdownFlow document for the seeded lesson. Blocks are separated by `---`:
#   0. preserved content block (emitted as-is, no LLM call)
#   1. LLM-generated content block (streams the fake completion)
#   2. buttons-only interaction block (assigns {{fav_color}}, no LLM
#      validation for matching button values)
#   3. final LLM-generated content block (runs after the interaction input)
GOLDEN_LESSON_MDFLOW = """!===
Welcome to the golden lesson. This block is preserved content.
!===

---

Introduce the golden regression harness in one short sentence.

---

?[%{{fav_color}} Red//red | Blue//blue]

---

Summarize the lesson and say goodbye.
"""

# Fixed multi-token completion used for every non-echo LLM call.
GOLDEN_LLM_CHUNKS = ["Hello ", "golden ", "learner."]


def _looks_like_json_object(text: str) -> bool:
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return False
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return False
    return True


def _iter_golden_completion(messages) -> list[str]:
    """Choose deterministic completion chunks for a chat call.

    markdown-flow asks the LLM to "translate" interaction button labels by
    sending a JSON object as the user message; echoing that JSON back keeps
    the reconstructed interaction content identical to the authored source.
    Every other prompt gets the fixed multi-token stream.
    """
    last_user_content = ""
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get("role") == "user":
            last_user_content = str(message.get("content", ""))
            break
    if _looks_like_json_object(last_user_content):
        return [last_user_content.strip()]
    return list(GOLDEN_LLM_CHUNKS)


def golden_chat_llm(*args, **kwargs):
    messages = kwargs.get("messages")
    if messages is None:
        for arg in args:
            if isinstance(arg, list) and arg and isinstance(arg[0], dict):
                messages = arg
                break
    chunks = _iter_golden_completion(messages)
    for idx, chunk in enumerate(chunks, start=1):
        yield FakeLLMResponse(
            chunk,
            chunk_id=f"golden-chat-{idx}",
            is_end=idx == len(chunks),
            finish_reason="stop" if idx == len(chunks) else None,
        )


def golden_invoke_llm(*args, **kwargs):
    yield from golden_chat_llm(*args, **kwargs)


def golden_get_allowed_models() -> list[str]:
    return []


def golden_get_current_models(_app) -> list[dict[str, str]]:
    return []


@pytest.fixture(autouse=True)
def golden_llm(monkeypatch):
    """Patch a deterministic fake LLM into every namespace the /run path uses."""
    import sys

    targets = {
        "flaskr.api.llm": (
            ("chat_llm", golden_chat_llm),
            ("invoke_llm", golden_invoke_llm),
            ("get_allowed_models", golden_get_allowed_models),
            ("get_current_models", golden_get_current_models),
        ),
        # context_v2 binds these names at import time.
        "flaskr.service.learn.context_v2": (
            ("chat_llm", golden_chat_llm),
            ("get_allowed_models", golden_get_allowed_models),
            ("get_current_models", golden_get_current_models),
        ),
        # check_text binds invoke_llm at import time.
        "flaskr.service.learn.check_text": (("invoke_llm", golden_invoke_llm),),
        # handle_input_ask resolves a module-level `chat_llm` global first.
        "flaskr.service.learn.handle_input_ask": (("chat_llm", golden_chat_llm),),
    }
    for module_path, attrs in targets.items():
        module = sys.modules.get(module_path)
        if module is None:
            __import__(module_path)
            module = sys.modules[module_path]
        for name, func in attrs:
            monkeypatch.setattr(module, name, func, raising=False)


@pytest.fixture(autouse=True)
def golden_sse_settings(app, monkeypatch):
    """Disable timing-dependent SSE heartbeats for deterministic transcripts."""
    monkeypatch.setitem(app.config, "SSE_HEARTBEAT_INTERVAL", 0)


@pytest.fixture(autouse=True)
def golden_disable_risk_audit_commit(monkeypatch):
    """Skip the risk-control audit side-write on SQLite.

    ``add_risk_control_result`` commits through a nested ``app.app_context()``
    (a second DB connection) while the /run producer transaction still holds
    the SQLite write lock, which deadlocks the single-writer test database
    (fine on MySQL). The audit row never appears in the SSE/JSON contract, so
    golden tests replace it with a no-op.
    """
    monkeypatch.setattr(
        "flaskr.service.learn.check_text.add_risk_control_result",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )


def mock_validate_user(monkeypatch, user_bid: str, *, is_creator: bool = False) -> None:
    """Route auth: make every request resolve to the given user."""
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


def seed_golden_user(app, user_bid: str) -> None:
    """Ensure a learner row exists for load_user_aggregate()."""
    import flaskr.dao as dao
    from flaskr.service.user.models import UserInfo

    with app.app_context():
        existing = UserInfo.query.filter_by(user_bid=user_bid).first()
        if existing:
            return
        dao.db.session.add(
            UserInfo(
                user_bid=user_bid,
                user_identify=f"{user_bid}@golden.test",
                nickname="Golden Learner",
                language="en-US",
                deleted=0,
            )
        )
        dao.db.session.commit()


@pytest.fixture
def golden_shifu(app):
    """Seed a published, free shifu with one chapter and one runnable lesson.

    Idempotent: existing golden rows are removed before reseeding so every
    test starts from the same published structure regardless of ordering.
    """
    import flaskr.dao as dao
    from flaskr.service.shifu.models import (
        LogPublishedStruct,
        PublishedOutlineItem,
        PublishedShifu,
    )
    from flaskr.service.shifu.shifu_history_manager import HistoryItem

    with app.app_context():
        PublishedShifu.query.filter_by(shifu_bid=GOLDEN_SHIFU_BID).delete()
        PublishedOutlineItem.query.filter_by(shifu_bid=GOLDEN_SHIFU_BID).delete()
        LogPublishedStruct.query.filter_by(shifu_bid=GOLDEN_SHIFU_BID).delete()

        shifu = PublishedShifu(
            shifu_bid=GOLDEN_SHIFU_BID,
            title="Golden Shifu",
            description="Deterministic course for golden regression fixtures",
            avatar_res_bid="",
            keywords="golden,regression",
            llm="gpt-test",
            llm_temperature=Decimal("0"),
            llm_system_prompt="",
            price=Decimal("0"),
            created_user_bid=GOLDEN_CREATOR_BID,
            updated_user_bid=GOLDEN_CREATOR_BID,
        )
        chapter = PublishedOutlineItem(
            outline_item_bid=GOLDEN_CHAPTER_BID,
            shifu_bid=GOLDEN_SHIFU_BID,
            title="Golden Chapter",
            position="1",
            type=402,
            hidden=0,
            content="",
        )
        lesson = PublishedOutlineItem(
            outline_item_bid=GOLDEN_LESSON_BID,
            shifu_bid=GOLDEN_SHIFU_BID,
            title="Golden Lesson",
            position="1.1",
            type=402,
            hidden=0,
            content=GOLDEN_LESSON_MDFLOW,
        )
        dao.db.session.add_all([shifu, chapter, lesson])
        dao.db.session.commit()

        struct = HistoryItem(
            bid=GOLDEN_SHIFU_BID,
            id=shifu.id,
            type="shifu",
            children=[
                HistoryItem(
                    bid=GOLDEN_CHAPTER_BID,
                    id=chapter.id,
                    type="outline",
                    children=[
                        HistoryItem(
                            bid=GOLDEN_LESSON_BID,
                            id=lesson.id,
                            type="outline",
                            children=[],
                        )
                    ],
                )
            ],
        ).to_json()
        dao.db.session.add(
            LogPublishedStruct(
                struct_bid="golden-struct-0001",
                shifu_bid=GOLDEN_SHIFU_BID,
                struct=struct,
            )
        )
        dao.db.session.commit()

    return SimpleNamespace(
        shifu_bid=GOLDEN_SHIFU_BID,
        chapter_bid=GOLDEN_CHAPTER_BID,
        lesson_bid=GOLDEN_LESSON_BID,
    )


def assert_or_update_golden(fixture_name: str, normalized_text: str) -> None:
    """Compare against the recorded fixture, or rewrite it in update mode."""
    fixture_path = FIXTURES_DIR / fixture_name
    if os.environ.get("UPDATE_GOLDEN") == "1":
        FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(normalized_text, encoding="utf-8")
        return
    if not fixture_path.exists():
        raise AssertionError(
            f"Golden fixture {fixture_path} is missing. "
            "Record it with UPDATE_GOLDEN=1 pytest tests/golden/ and commit the file."
        )
    expected = fixture_path.read_text(encoding="utf-8")
    if normalized_text != expected:
        raise AssertionError(
            f"Golden fixture mismatch for {fixture_name}.\n"
            "The normalized output no longer matches the recorded contract. "
            "Review the diff below; if the change is intentional, rerun with "
            "UPDATE_GOLDEN=1 and commit the updated fixture.\n"
            f"--- expected ({fixture_path})\n{expected}\n"
            f"+++ actual\n{normalized_text}"
        )
