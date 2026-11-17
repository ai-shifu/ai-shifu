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
    # The concise-instructions revision intentionally updates all runtime prose.
    # Keep historical migration evidence intact and pin the reviewed current text.
    hashes.update(
        {
            "answer_review": (
                "ab3e480b1e99a067e0d5a1e4213059f548802a8ccbcbb1f33c773fa4788cafbf"
            ),
            "exercise_statistics": (
                "4ef0db27013dd10942865c1d8bf3ea047e0029845738713cfb357248dc09a197"
            ),
            "feedback_contract": (
                "b54bfbf78f43b316fce27cdbf62638d8a0237f2098ac35ecbe86c813fd6d31d4"
            ),
            "html_display": (
                "0608057a58b538355f35a1a48975beda82a861247671d8950911ce9128a74b80"
            ),
            "html_display_generic": (
                "41d40abe6b03a8eb99fd2aea10b2c0b3de922fa8c9c45c592e80fb48bc0dd8b2"
            ),
            "listen_mode": (
                "ee65eee13c65bb12ea824dc5e98df8b876eacbb0ab77863944a509931ca159dd"
            ),
            "memory_admission": (
                "fe46f2c8ad596c5d35633ca57058936a5c5efb87f39b0da3db618ff04202e361"
            ),
            "memory_policy": (
                "34996bdf327f4d60752352e3101d00f65874fb5db747336f9ad88bea70e4e7a2"
            ),
            "memory_recall": (
                "68d3337e091486cdf88ea849172c5aa80eb4e49857b2b6ccfe6fc039598f0ebe"
            ),
            "memory_unrestricted": (
                "89c151f5401944e13e726f453f3a661a59e9dc29749c1d613cb15c71d3d99544"
            ),
            "recall_history_compaction": (
                "a8d00fdf79156aa143dd0c35331bd0d9f0f022f99a7e46dd7ddc819f0c68e5b7"
            ),
            "v1_syntax": (
                "1930fc65af1ffbda72341990fc53c0b9c4f66c0f156dba828c751cc4f8f7e29f"
            ),
            "system": (
                "76f71eb4f97ec55a08f44b17a0b4f68f5bbefb6e27822dd464f72d9412691aae"
            ),
        }
    )
    # Removed teaching-history compaction is not part of the current package.
    del hashes["teaching_history_compaction"], hashes["teaching_summary"]
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
