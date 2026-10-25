"""Exercise the library without loading an application or its old package path."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from markdownflow import Engine, InteractionResponseTurn, Session, load_prompt
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

_API_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_SESSION = Path(__file__).parent / "fixtures" / "legacy_session.json"


def test_bundled_prompts_change_only_for_the_question_contract() -> None:
    fixture = Path(__file__).parent / "fixtures" / "legacy_prompt_hashes.json"
    hashes = json.loads(fixture.read_text())["sha256"]
    assert len(hashes) == 15
    question_hashes = {
        "answer_review": "8d576266ffb50bc4233836a614647d783602c2c7ed6d7c9416fe5d5d1182638d",
        "feedback_contract": "c2ff1f430b29498a2cec96a3a0b349ab7f6a9f788699cc6c85dab902f21343fa",
        "memory_policy": "80a141d8c03c942b333884bc9b91296f7afc39ecdf7981cd95112b2b388f94ea",
        "memory_unrestricted": "beadeaf631a8e48715aabaac68032bf1ea585e1b47ce743d4cafdb4504e3a7f2",
        "system": "63ea8d1511a4664544c8b18d5316d164ec5fdde8b8f98d94a2b2a335f45c21d9",
        "v1_syntax": "58afbecfd4b976000b48415de4baab019f81c49a8c0aa6a3ba815e4aa001d653",
    }
    assert question_hashes.keys() <= hashes.keys()
    hashes.update(question_hashes)
    for name, expected in hashes.items():
        assert hashlib.sha256(load_prompt(name).encode("utf-8")).hexdigest() == expected


def test_prompt_lookup_rejects_paths_and_reports_a_missing_resource() -> None:
    for name in ("../system", "system.md", ""):
        with pytest.raises(ValueError, match="lowercase identifier"):
            load_prompt(name)
    with pytest.raises(FileNotFoundError, match="not_a_bundled_prompt"):
        load_prompt("not_a_bundled_prompt")


def test_copied_library_runs_without_an_application(tmp_path: Path) -> None:
    """Import and execute the copied artifact without the repository's Flask tree."""
    shutil.copytree(
        _API_ROOT / "markdownflow",
        tmp_path / "markdownflow",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    program = r"""
import importlib.abc
import sys

sys.path.insert(0, sys.argv[1])

class RejectApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "flaskr" or fullname.startswith("flaskr."):
            raise AssertionError("library imported the application: " + fullname)

sys.meta_path.insert(0, RejectApplication())

from markdownflow import (
    ContentDelta, Engine, InteractionSpec, LessonPager, Prompts,
    QuestionLabels, QuestionRenderer, iter_turn,
)
from pydantic_ai.models.function import FunctionModel

renderer = QuestionRenderer(QuestionLabels(
    continue_label="Proceed", free_text_placeholder="Your response",
))
assert "Your response" in renderer.render_interaction(
    InteractionSpec(type="text", prompt="Describe your goal."),
)
assert Prompts.default().base
assert LessonPager().add("Content.") is not None

async def stream(messages, info):
    yield "Public content."

async def events():
    engine = Engine(FunctionModel(stream_function=stream))
    session = await engine.new_session("Explain the first step.")
    async for event in engine.run_turn(session):
        yield event

events = list(iter_turn(events))
assert "".join(e.text for e in events if isinstance(e, ContentDelta)) == "Public content."
assert not any(name == "flaskr" or name.startswith("flaskr.") for name in sys.modules)
assert "flask" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", program, str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.anyio
async def test_legacy_package_session_resumes_its_remaining_pending_answer() -> None:
    """Read real old-package output, including an answer collected before relocation.

    The fixture was produced with FunctionModel through the old
    flaskr.service.learn.agent.engine at commit
    main commit 5991ac21a05ad992aa6ff4ae80c052970aa4e06b. It raised two questions, accepted
    only the first, then serialized the session. IDs and timestamps were fixed
    for an inspectable fixture; the serialized messages and pending schema are
    the old serializer's output.
    """
    payload = _LEGACY_SESSION.read_text()
    assert "flaskr." not in payload
    state = json.loads(payload)
    session = Session.loads(payload)
    assert session.memory_generations == {}
    expected = {**state, "memory_generations": {}}
    expected["initial_memory"] = expected.pop("initial_variables")
    for pending in expected["pending"]:
        pending["spec"]["question"] = pending["spec"].pop("variable")
    expected["messages"] = json.loads(
        ModelMessagesTypeAdapter.dump_json(
            ModelMessagesTypeAdapter.validate_python(expected["messages"])
        )
    )
    assert session.to_dict() == expected
    assert session.answers == {"legacy-role": "Learner wrote: Data analyst"}
    assert [item.tool_call_id for item in session.pending] == ["legacy-goal"]
    assert session.answered_memory_keys() == {"role"}
    assert session.user_memory == {"pace": "slow"}
    assert session.teaching_summaries == {"legacy-summary": "Prior teaching."}
    assert session.usage == {"requests": 2, "input_tokens": 123, "output_tokens": 45}
    calls = 0

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if any(
            isinstance(part, ToolReturnPart) and part.tool_name == "finish"
            for part in messages[-1].parts
        ):
            yield " "
            return
        returns = {
            part.tool_call_id: part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "interact"
        }
        assert returns == {
            "legacy-role": "Learner wrote: Data analyst",
            "legacy-goal": "Learner wrote: Learn statistics",
        }
        yield {
            0: DeltaToolCall(
                name="finish",
                json_args='{"summary":"Both answers collected."}',
                tool_call_id="relocated-finish",
            )
        }

    engine = Engine(FunctionModel(stream_function=stream))
    _ = [
        event
        async for event in engine.run_turn(
            session,
            InteractionResponseTurn(id="legacy-goal", text="Learn statistics"),
        )
    ]
    assert calls == 2
    assert session.finished
    assert not session.pending
    assert session.memory == {"role": "Data analyst", "goal": "Learn statistics"}
    restored = Session.loads(session.dumps())
    assert restored.finished
    assert restored.memory == session.memory
    assert restored.answered_memory_keys() == {"role", "goal"}
