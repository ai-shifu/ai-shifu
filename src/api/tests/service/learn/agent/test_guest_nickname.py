"""Keep empty canonical nicknames out of the learner-facing lesson script."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.i18n import clear_language, set_language
from flaskr.service.learn.agent import run_agent, session_store
from flaskr.service.learn.agent.engine import Engine
from flaskr.service.learn.learn_dtos import GeneratedType
from flaskr.service.learn.memory import load_memory
from flaskr.service.profile.models import VariableValue
from flaskr.service.user.repository import create_user_entity, get_user_entity_by_bid
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from flask import Flask


@pytest.mark.parametrize(
    ("nickname", "language", "address"),
    [
        ("", "en-US", "Learner"),
        (None, "en-US", "Learner"),
        (" \n\t", "en-US", "Learner"),
        ("", "zh-CN", "\u540c\u5b66"),
        ("", "fr-FR", "Apprenant"),
        ("", "de-DE", "Lernende Person"),
        ("", "es-ES", "Estudiante"),
        ("", "ar-SA", "\u0627\u0644\u0645\u062a\u0639\u0644\u0645"),
        ("", "th-TH", "\u0e1c\u0e39\u0e49\u0e40\u0e23\u0e35\u0e22\u0e19"),
        ("", "ur-PK", "\u0637\u0627\u0644\u0628 \u0639\u0644\u0645"),
        ("", "unknown-locale", "Learner"),
        ("Alex", "zh-CN", "Alex"),
    ],
)
def test_nickname_reaches_the_model_without_changing_the_profile(
    app: Flask, nickname: str | None, language: str, address: str
) -> None:
    """Use the learner's locale for a presentation fallback, never a saved nickname."""
    user, course, lesson = uuid4().hex, uuid4().hex, uuid4().hex
    seen: list[str] = []

    async def model(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str]:
        seen.extend(
            part.content
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, UserPromptPart) and isinstance(part.content, str)
        )
        yield "Here is the example."

    def drive(make_events: Callable, **_kwargs: object) -> Iterator:
        async def collect() -> list:
            return [event async for event in make_events()]

        return iter(asyncio.run(collect()))

    with app.app_context():
        with unit_of_work():
            create_user_entity(
                user_bid=user, identify=user, nickname=nickname, language=language
            )
        original = load_memory(app, user, course).as_variables()
        # A browser/UI locale must not override the learner's lesson language.
        set_language("es-ES")
        try:
            events = list(
                run_agent.run_agent_lesson(
                    app,
                    engine=Engine(FunctionModel(stream_function=model)),
                    script="Hello {{sys_user_nickname}}. Keep {{unknown}} for later.",
                    teaching_brief="Address {{sys_user_nickname}} directly.",
                    user_bid=user,
                    shifu_bid=course,
                    outline_bid=lesson,
                    iter_turn=drive,
                )
            )
        finally:
            clear_language()
        assert events[-1].type == GeneratedType.BREAK
        prompt = seen[0]
        memory = json.loads(prompt.split("<memory>\n", 1)[1].split("\n</memory>", 1)[0])
        assert memory["sys_user_nickname"] == address
        assert f"Hello {address}." in prompt
        assert f"Address {address} directly." in prompt
        assert "{{sys_user_nickname}}" not in prompt
        assert "{{unknown}}" in prompt
        db.session.remove()
        assert get_user_entity_by_bid(user).nickname == (nickname or "")
        assert load_memory(app, user, course).as_variables() == original
        assert VariableValue.query.filter_by(user_bid=user).count() == 0
        saved = session_store.load_agent_session(app, user, lesson)
        assert saved.user_memory["sys_user_nickname"] == address
