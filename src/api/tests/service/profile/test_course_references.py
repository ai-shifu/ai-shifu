"""Verify explicit same-owner references against real revisioned SQLite records."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.memory import load_memory
from flaskr.service.learn.utils_v2 import get_fmt_prompt
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import get_user_profiles, save_user_profiles
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.repository import create_user_entity

if TYPE_CHECKING:
    from collections.abc import Iterator

    from flask import Flask


@pytest.fixture
def context(app: Flask) -> Iterator[SimpleNamespace]:
    """Create two owned published courses, an explicit destination reference and one value."""
    owner, user, source, target, outline = (uuid4().hex for _ in range(5))
    key = f"course:{source}:goal"
    with app.app_context():
        with unit_of_work():
            create_user_entity(user_bid=user, identify=user, nickname="Learner")
            for course in (source, target):
                db.session.add(DraftShifu(shifu_bid=course, created_user_bid=owner))
                db.session.add(PublishedShifu(shifu_bid=course, created_user_bid=owner))
            db.session.add(
                Variable(shifu_bid=target, key=key, variable_bid=uuid4().hex)
            )
            db.session.add(
                Variable(shifu_bid=target, key="goal", variable_bid=uuid4().hex)
            )
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=target,
                    outline_item_bid=outline,
                    content=f"Use {{{{{key}}}}}.",
                )
            )
            db.session.add(
                VariableValue(
                    user_bid=user,
                    shifu_bid=source,
                    key="goal",
                    value="Source goal",
                    variable_value_bid=uuid4().hex,
                )
            )
        yield SimpleNamespace(
            app=app,
            owner=owner,
            user=user,
            source=source,
            target=target,
            outline=outline,
            key=key,
            reference_text=f"Use {{{{{key}}}}}.",
        )
        with unit_of_work():
            VariableValue.query.filter(
                VariableValue.user_bid.in_([user, owner])
            ).delete()
            Variable.query.filter(
                (Variable.shifu_bid.in_([source, target]))
                | (Variable.key.startswith(f"course:{source}:"))
            ).delete()
            DraftOutlineItem.query.filter_by(shifu_bid=target).delete()
            PublishedOutlineItem.query.filter_by(shifu_bid=target).delete()
            for model in (DraftShifu, PublishedShifu):
                model.query.filter(model.shifu_bid.in_([source, target])).delete()


def _profiles(context: SimpleNamespace) -> dict:
    """Resolve only the author text carried by this simulated lesson request."""
    return get_user_profiles(
        context.app, context.user, context.target, reference_text=context.reference_text
    )


def _value(context: SimpleNamespace, value: str, **fields: object) -> VariableValue:
    """Append a value without modifying any prior version."""
    fields = {
        "user_bid": context.user,
        "shifu_bid": context.source,
        "key": "goal",
        **fields,
    }
    with unit_of_work():
        row = VariableValue(**fields, value=value, variable_value_bid=uuid4().hex)
        db.session.add(row)
    return row


def _published_text(context: SimpleNamespace, content: str, **fields: object) -> None:
    """Append the destination outline's next published revision."""
    with unit_of_work():
        db.session.add(
            PublishedOutlineItem(
                shifu_bid=context.target,
                outline_item_bid=context.outline,
                content=content,
                **fields,
            )
        )


def _follow_up(context: SimpleNamespace, **kwargs: object) -> object:
    """Build real follow-up prompts while isolating unrelated conversation queries."""
    from flaskr.service.learn.follow_up_context import (
        build_follow_up_conversation_context,
    )

    return build_follow_up_conversation_context(
        context.app,
        user_info=SimpleNamespace(user_id=context.user),
        shifu_bid=context.target,
        outline_item_bid=context.outline,
        progress_record_bid="reference-follow-up",
        follow_up_info=SimpleNamespace(ask_prompt="{shifu_system_message}"),
        course_system_prompt=kwargs.pop("course_system_prompt", context.reference_text),
        use_learner_language=False,
        runtime_language="en-US",
        **kwargs,
    )


@pytest.mark.parametrize("prefix", ["course:", "share:"])
@pytest.mark.parametrize("supplement", [False, True])
def test_author_declarations_cannot_read_other_courses(
    context: SimpleNamespace, prefix: str, supplement: bool
) -> None:
    c = context
    key = f"{prefix}{c.source}:goal"
    text = f"Use {{{{{key}}}}} and collect %{{{{{key}}}}}."
    with unit_of_work():
        db.session.add(Variable(shifu_bid=c.target, key=key, variable_bid=uuid4().hex))
        db.session.add(
            VariableValue(
                user_bid=c.user, shifu_bid=c.target, key=key, value="Forged local alias"
            )
        )
    _published_text(c, text)
    _value(c, "Destination goal", shifu_bid=c.target)
    result = load_memory(
        c.app,
        c.user,
        c.target,
        include_course_variables=supplement,
        reference_text=text,
    ).as_variables()
    assert key not in result
    assert result["goal"] == "Destination goal"
    assert "Source goal" not in get_fmt_prompt(c.app, c.user, c.target, text)
    assert "Forged local alias" not in str(result)


def test_registered_system_fields_are_global_but_custom_values_have_no_global_fallback(
    context: SimpleNamespace,
) -> None:
    c = context
    with unit_of_work():
        db.session.add(
            Variable(shifu_bid=c.target, key="sys_user_style", variable_bid=uuid4().hex)
        )
    _value(c, "Legacy global custom", shifu_bid="")
    _value(c, "Examples first", shifu_bid="", key="sys_user_style")
    _value(c, "Course nickname spoof", shifu_bid=c.target, key="sys_user_nickname")
    for course in (c.source, c.target):
        data = get_user_profiles(c.app, c.user, course)
        assert data["sys_user_nickname"] == "Learner"
    data = load_memory(c.app, c.user, c.target, include_course_variables=True).variables
    assert "goal" not in data
    assert data["sys_user_style"] == "Examples first"
    assert "Legacy global custom" not in str(data)
    _value(c, "Local goal", shifu_bid=c.target)
    assert get_user_profiles(c.app, c.user, c.target)["goal"] == "Local goal"
    with unit_of_work():
        db.session.add(
            Variable(shifu_bid=c.source, key="goal", variable_bid=uuid4().hex)
        )
    assert get_user_profiles(c.app, c.user, c.source)["goal"] == "Source goal"


@pytest.mark.parametrize(
    "prefix", ["course:", "share:", "course:malformed", "share:malformed"]
)
@pytest.mark.parametrize("writer", ["profile", "settings", "memory"])
def test_all_write_adapters_drop_retired_aliases(
    context: SimpleNamespace, prefix: str, writer: str
) -> None:
    from flaskr.service.learn.memory import (
        MemoryUpdate,
        VariableMemoryUpdate,
        stage_memory,
    )
    from flaskr.service.profile.funcs import update_user_profile_with_lable

    c = context
    key = f"{prefix}{c.source}:goal"
    before = [(v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)]
    with unit_of_work():
        if writer == "profile":
            save_user_profiles(
                c.app, c.user, c.target, [ProfileToSave(key, "Overwrite", "")]
            )
        elif writer == "settings":
            update_user_profile_with_lable(
                c.app, c.user, [{"key": key, "value": "Overwrite"}], course_id=c.target
            )
        else:
            patch = MemoryUpdate(variables=[VariableMemoryUpdate(key, "Overwrite")])
            stage_memory(c.app, c.user, c.target, patch)
            assert not patch.variables
    assert [
        (v.id, v.value) for v in VariableValue.query.order_by(VariableValue.id)
    ] == before


@pytest.mark.parametrize("prefix", ["course:", "share:"])
def test_follow_up_and_voice_cannot_read_course_aliases(
    context: SimpleNamespace, prefix: str
) -> None:
    c = context
    key = f"{prefix}{c.source}:goal"
    text = f"Use {{{{{key}}}}}."
    with unit_of_work():
        db.session.add(Variable(shifu_bid=c.target, key=key, variable_bid=uuid4().hex))
    _published_text(c, text)
    result = _follow_up(c, course_system_prompt=text)
    assert "Source goal" not in result.system_instruction
    assert all(
        "Source goal" not in item["content"] for item in result.provider_messages
    )
    result = _follow_up(
        c, course_system_prompt=None, fallback_system_prompt="Voice instruction"
    )
    assert "Source goal" not in result.system_instruction


def test_formatter_does_not_resolve_retired_aliases_even_from_a_supplied_snapshot() -> (
    None
):
    from flaskr.service.learn.utils_v2 import extract_variables, safe_format_template

    for prefix in ("course:", "share:"):
        name = prefix + "a" * 32 + ":goal"
        template = f"{{{{{name}}}}} {{goal}} {{goal:>12}}"
        assert set(extract_variables(template)) == {"goal"}
        assert (
            safe_format_template(template, {name: "Foreign", "goal": "Local"})
            == f"{{{{{name}}}}} Local {{goal:>12}}"
        )
