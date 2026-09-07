"""Keep course instructions out of Live while retaining follow-up context."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask
from flaskr.service.learn import follow_up_context as context
from flaskr.service.learn import live_follow_up_routes as routes
from flaskr.service.learn.gemini_live_token import GeminiLiveHistoryTurn
from flaskr.service.learn.live_follow_up_session_store import LiveFollowUpSessionBinding
from flaskr.util.prompt_loader import load_prompt_template


@pytest.mark.parametrize("preview_mode", [False, True])
@pytest.mark.parametrize("learning_mode", ["read", "listen"])
@pytest.mark.parametrize(
    "ask_prompt",
    ["", " \n ", "FOLLOW-UP\n{shifu_system_message}", "Follow-up instructions only."],
)
def test_live_context_omits_course_prompt_and_preserves_follow_up_context(
    monkeypatch: pytest.MonkeyPatch,
    preview_mode: bool,
    learning_mode: str,
    ask_prompt: str,
) -> None:
    """Both learner and preview sessions omit course-prompt lookup and fallback."""
    app = Flask("live-context-test")
    binding = LiveFollowUpSessionBinding(
        session_bid="session-1",
        user_bid="user-1",
        shifu_bid="course-1",
        outline_bid="lesson-1",
        anchor_element_bid="anchor-1",
        progress_record_bid="progress-1",
        preview_mode=preview_mode,
        origin="https://learn.example.com",
        model=routes.GEMINI_LIVE_MODEL_ID,
        voice_name="Kore",
        language="zh-CN",
        learning_mode=learning_mode,
        expires_at_epoch=900,
    )
    captured: dict[str, object] = {}
    history = [
        {"role": "assistant", "content": "Current learning content"},
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier answer"},
    ]

    def reject_course_prompt(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Live must not load or inherit the course system prompt")

    def load_language(**kwargs: object) -> bool:
        captured["language_scope"] = kwargs
        return True

    def load_history(**kwargs: object) -> list[dict[str, str]]:
        captured["history_scope"] = kwargs
        return history

    def format_prompt(
        _app: Flask,
        _user_bid: str,
        _shifu_bid: str,
        prompt: str,
        *,
        resolved_profiles: dict[str, object],
    ) -> str:
        captured["profiles"] = resolved_profiles
        captured["base_prompt"] = prompt
        return prompt

    monkeypatch.setattr(
        routes, "resolve_course_system_prompt", reject_course_prompt, raising=False
    )
    monkeypatch.setattr(context, "resolve_course_system_prompt", reject_course_prompt)
    monkeypatch.setattr(
        routes,
        "load_user_aggregate",
        lambda _bid: SimpleNamespace(user_id="user-1", user_bid="user-1", identify=""),
    )
    monkeypatch.setattr(routes, "_load_use_learner_language", load_language)
    monkeypatch.setattr(
        context,
        "get_user_profiles",
        lambda *_args: {
            "sys_user_nickname": "Alex",
            "sys_user_background": "Synthetic learner background",
        },
    )
    monkeypatch.setattr(context, "get_fmt_prompt", format_prompt)
    monkeypatch.setattr(context, "load_follow_up_history", load_history)

    instruction, turns = routes._build_conversation(
        app,
        binding=binding,
        follow_up_info=SimpleNamespace(ask_prompt=ask_prompt),
    )

    voice_prompt = load_prompt_template("live_follow_up").strip()
    base_prompt = captured["base_prompt"]
    assert voice_prompt in base_prompt
    assert '"Alex"' in base_prompt
    assert '"Synthetic learner background"' in base_prompt
    assert "{shifu_system_message}" not in instruction
    if ask_prompt.strip() and "{shifu_system_message}" not in ask_prompt:
        assert instruction.startswith(ask_prompt)
    else:
        assert instruction.count(voice_prompt) == 1
        assert '"Synthetic learner background"' in instruction
        if ask_prompt.strip():
            assert instruction.startswith("FOLLOW-UP\n")
    assert instruction.endswith("IMPORTANT: You MUST respond in 简体中文.")
    assert captured["profiles"]["sys_user_language"] == "zh-CN"
    assert captured["language_scope"] == {
        "shifu_bid": "course-1",
        "preview_mode": preview_mode,
    }
    assert captured["history_scope"]["anchor_element_bid"] == "anchor-1"
    assert captured["history_scope"]["progress_record_bid"] == "progress-1"
    assert captured["history_scope"]["max_history_messages"] == 20
    assert turns == tuple(
        GeminiLiveHistoryTurn(role=item["role"], text=item["content"])
        for item in history
    )
