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
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic_ai.messages import ModelMessage
    from pydantic_ai.models.function import AgentInfo

_API_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_SESSION = Path(__file__).parent / "fixtures" / "legacy_session.json"


def test_bundled_prompts_only_update_reviewed_runtime_guidance() -> None:
    fixture = Path(__file__).parent / "fixtures" / "legacy_prompt_hashes.json"
    hashes = json.loads(fixture.read_text())["sha256"]
    assert len(hashes) == 15
    # Reference/binding and question-presentation guidance are reviewed changes;
    # retain every other copied prompt byte and keep the historical fixture intact.
    hashes["system"] = (
        "76869f643f131d6e0ce073a8b248c990417a57c1fef5405458200749953cbc7b"
    )
    hashes["v1_syntax"] = (
        "9a8edded890cbc6b7d1d4c12f47e10401ca4679917e21ac36272894e8c4251c2"
    )
    hashes["memory_policy"] = (
        "029a5cc7f0e74456df4c5a8b263f3b48a65758283d95ae11a66c8752f4d9d1dd"
    )
    hashes["memory_unrestricted"] = (
        "26f8f7ab22952281f88eea3025553b2ba18f2d01a50e4919036d9bf4a96a13cd"
    )
    hashes["answer_review"] = (
        "24405941f019dfd09ec49114b0e70261eefeda2bf8cbaace7ead55e6a788458a"
    )
    hashes["feedback_contract"] = (
        "0ed7209037a211f5e4276f1c4504620d53e476b8de1644c35e24793e716375b8"
    )
    # Teaching history compaction was removed: its prompts are gone, and recall
    # guidance no longer points at the read_teaching tool.
    del hashes["teaching_history_compaction"], hashes["teaching_summary"]
    hashes["memory_recall"] = (
        "a54d37a19b6018c25778cbbec1d47c6d28d965c6288654b365fff83dfea92e44"
    )
    hashes["recall_history_compaction"] = (
        "cd7e579720e5c03511ba93eb51ef6e37d29eac132abdf9f6a303080b7dbf6834"
    )
    for name, expected in hashes.items():
        # Keep the historical fixture intact while loading the renamed resource.
        current_name = "syntax" if name == "v1_syntax" else name
        assert (
            hashlib.sha256(load_prompt(current_name).encode("utf-8")).hexdigest()
            == expected
        )


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
assert Prompts.default().syntax
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
    # Pydantic AI 2.53 serializes these new defaults while reading the unchanged
    # legacy fixture. Keep every historical field in the exact comparison below.
    for message in state["messages"]:
        if message["kind"] == "response":
            message["workspace_ref"] = None
            message["usage"]["audio_seconds"] = 0.0
    # The removed teaching summary cache is dropped on load.
    assert state.pop("teaching_summaries") == {"legacy-summary": "Prior teaching."}
    assert session.to_dict() == {**state, "memory_generations": {}}
    assert session.answers == {"legacy-role": "Learner wrote: Data analyst"}
    assert [item.tool_call_id for item in session.pending] == ["legacy-goal"]
    assert session.answered_memory_keys() == {"role"}
    assert session.user_memory == {"pace": "slow"}
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
    assert calls == 1
    assert session.finished
    assert not session.pending
    assert session.memory == {"role": "Data analyst", "goal": "Learn statistics"}
    restored = Session.loads(session.dumps())
    assert restored.finished
    assert restored.memory == session.memory
    assert restored.answered_memory_keys() == {"role", "goal"}
