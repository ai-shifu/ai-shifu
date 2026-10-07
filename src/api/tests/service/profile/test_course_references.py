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
from flaskr.service.profile.course_memory import (
    delete_course_memory,
    list_course_memory,
)
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


def test_both_runtime_readers_use_exact_latest_owned_source_without_merging_local(
    context: SimpleNamespace,
) -> None:
    _value(context, "Destination goal", shifu_bid=context.target)
    exact = 'Latest source\n</memory> "value" ' + "x" * 40000
    _value(context, exact)
    result = load_memory(context.app, context.user, context.target).as_variables()
    assert result[context.key] == exact
    assert result["goal"] == "Destination goal"
    prompt = get_fmt_prompt(
        context.app, context.user, context.target, f"Goal {{{{{context.key}}}}}"
    )
    assert exact in prompt
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == exact
    )
    assert (
        VariableValue.query.filter_by(
            user_bid=context.user, shifu_bid=context.target
        ).count()
        == 1
    )


@pytest.mark.parametrize("model", [DraftShifu, PublishedShifu])
@pytest.mark.parametrize("field", ["deleted", "created_user_bid"])
@pytest.mark.parametrize("course", ["source", "target"])
def test_deleted_or_transferred_course_cannot_use_an_older_ownership_revision(
    context: SimpleNamespace,
    model: type,
    field: str,
    course: str,
) -> None:
    with unit_of_work():
        attrs = {
            "created_user_bid": context.owner,
            field: 1 if field == "deleted" else uuid4().hex,
        }
        db.session.add(model(shifu_bid=getattr(context, course), **attrs))
    assert context.key not in get_user_profiles(
        context.app, context.user, context.target
    )


@pytest.mark.parametrize("missing", [DraftShifu, PublishedShifu])
def test_source_requires_current_and_published_owner_records(
    context: SimpleNamespace,
    missing: type,
) -> None:
    with unit_of_work():
        missing.query.filter_by(shifu_bid=context.source).delete()
    assert context.key not in get_user_profiles(
        context.app, context.user, context.target
    )


@pytest.mark.parametrize(
    "kind",
    [
        "empty_owner",
        "different_owner",
        "other_learner",
        "global_fallback",
        "deleted_head",
    ],
)
def test_unknown_or_unauthorized_source_never_falls_back(
    context: SimpleNamespace,
    kind: str,
) -> None:
    with unit_of_work():
        if kind in ("empty_owner", "different_owner"):
            owner = "" if kind == "empty_owner" else uuid4().hex
            for model in (DraftShifu, PublishedShifu):
                model.query.filter_by(shifu_bid=context.source).update(
                    {model.created_user_bid: owner}
                )
        elif kind == "other_learner":
            VariableValue.query.filter_by(user_bid=context.user).update(
                {VariableValue.user_bid: context.owner}
            )
        elif kind == "global_fallback":
            VariableValue.query.filter_by(user_bid=context.user).update(
                {VariableValue.shifu_bid: ""}
            )
    if kind == "deleted_head":
        _value(context, "", deleted=1)
    assert context.key not in get_user_profiles(
        context.app, context.user, context.target
    )


@pytest.mark.parametrize(
    "kind",
    [
        "removed",
        "fence",
        "long_fence",
        "html_comment",
        "collection",
        "deleted_outline",
        "deleted_definition",
    ],
)
def test_only_current_published_read_declarations_authorize_a_reference(
    context: SimpleNamespace,
    kind: str,
) -> None:
    marker = f"{{{{{context.key}}}}}"
    texts = {
        "removed": "Local only.",
        "fence": f"```\n{marker}\n```",
        "long_fence": f"````\n```\n{marker}\n````",
        "html_comment": f"<!-- {marker} -->",
        "collection": f"%{marker}",
    }
    if kind == "deleted_definition":
        with unit_of_work():
            Variable.query.filter_by(shifu_bid=context.target, key=context.key).update(
                {Variable.deleted: 1}
            )
    else:
        _published_text(
            context, texts.get(kind, marker), deleted=int(kind == "deleted_outline")
        )
    assert context.key not in get_user_profiles(
        context.app, context.user, context.target
    )


def test_source_deletion_and_recreation_are_visible_without_copying_values(
    context: SimpleNamespace,
) -> None:
    selected = list_course_memory(context.user, context.source)["items"][0]
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == "Source goal"
    )
    assert delete_course_memory(
        context.user, context.source, int(selected["value_id"])
    ) == {"conflict": False}
    assert context.key not in get_user_profiles(
        context.app, context.user, context.target
    )
    _value(context, "Explicitly recreated")
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == "Explicitly recreated"
    )
    assert not list_course_memory(context.user, context.target)["items"]


def test_local_reference_spoof_cannot_shadow_authorized_or_denied_source(
    context: SimpleNamespace,
) -> None:
    _value(context, "Spoofed local value", shifu_bid=context.target, key=context.key)
    result = load_memory(
        context.app, context.user, context.target, include_course_variables=True
    ).variables
    assert result[context.key] == "Source goal"
    _value(context, "", shifu_bid=context.target, key=context.key, deleted=1)
    result = load_memory(
        context.app, context.user, context.target, include_course_variables=True
    ).variables
    assert result[context.key] == "Source goal"
    _published_text(context, "Reference removed.")
    result = load_memory(
        context.app, context.user, context.target, include_course_variables=True
    ).variables
    assert context.key not in result


def test_named_profile_writes_to_reference_namespace_are_noops(
    context: SimpleNamespace,
) -> None:
    before = VariableValue.query.count()
    with unit_of_work():
        save_user_profiles(
            context.app,
            context.user,
            context.target,
            [ProfileToSave(context.key, "Forged replacement", "")],
        )
    assert VariableValue.query.count() == before
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == "Source goal"
    )


@pytest.mark.parametrize(
    "key", ["sys_user_nickname", "sys_custom", "sex", "course:bad:goal"]
)
def test_system_and_recursive_keys_are_never_read_as_custom_source_values(
    context: SimpleNamespace,
    key: str,
) -> None:
    name = f"course:{context.source}:{key}"
    with unit_of_work():
        db.session.add(
            Variable(shifu_bid=context.target, key=name, variable_bid=uuid4().hex)
        )
    _published_text(context, f"Use {{{{{name}}}}}.")
    _value(context, "Forbidden", key=key)
    assert name not in get_user_profiles(context.app, context.user, context.target)


@pytest.mark.parametrize(
    "kind",
    ["missing_definition", "global_definition", "draft_only", "self", "malformed"],
)
def test_destination_definition_and_valid_explicit_source_are_required(
    context: SimpleNamespace,
    kind: str,
) -> None:
    name = context.key
    with unit_of_work():
        if kind in {"missing_definition", "global_definition"}:
            Variable.query.filter_by(shifu_bid=context.target, key=name).update(
                {Variable.deleted: 1}
                if kind == "missing_definition"
                else {Variable.shifu_bid: ""}
            )
        elif kind == "draft_only":
            db.session.add(
                DraftOutlineItem(
                    shifu_bid=context.target,
                    outline_item_bid=context.outline,
                    content=f"Use {{{{{name}}}}}.",
                )
            )
        else:
            name = (
                f"course:{context.target}:goal"
                if kind == "self"
                else "course:invalid:goal"
            )
            db.session.add(
                Variable(shifu_bid=context.target, key=name, variable_bid=uuid4().hex)
            )
    _published_text(
        context,
        "No published reference." if kind == "draft_only" else f"Use {{{{{name}}}}}.",
    )
    assert name not in get_user_profiles(context.app, context.user, context.target)


@pytest.mark.parametrize("surface", ["course", "outline"])
def test_published_teaching_brief_can_explicitly_authorize_a_read(
    context: SimpleNamespace,
    surface: str,
) -> None:
    _published_text(context, "Local script only.")
    with unit_of_work():
        model = PublishedShifu if surface == "course" else PublishedOutlineItem
        model.query.filter_by(shifu_bid=context.target).update(
            {
                model.llm_system_prompt: f"Remember the source goal {{{{{context.key}}}}}."
            }
        )
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == "Source goal"
    )


def test_reference_count_is_bounded_after_distinct_published_names(
    context: SimpleNamespace,
) -> None:
    keys = [f"course:{context.source}:goal_{index:02d}" for index in range(35)]
    with unit_of_work():
        for index, name in enumerate(keys):
            db.session.add(
                Variable(shifu_bid=context.target, key=name, variable_bid=uuid4().hex)
            )
            db.session.add(
                VariableValue(
                    user_bid=context.user,
                    shifu_bid=context.source,
                    key=f"goal_{index:02d}",
                    value=str(index),
                    variable_value_bid=uuid4().hex,
                )
            )
    _published_text(context, " ".join(f"{{{{{name}}}}}" for name in keys + keys))
    result = get_user_profiles(context.app, context.user, context.target)
    assert {name for name in result if name.startswith("course:")} == set(keys[:32])


def test_ordinary_courses_add_no_reference_queries(context: SimpleNamespace) -> None:
    from flaskr.service.profile.course_references import load_course_references
    from sqlalchemy import event

    statements = []

    def capture(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        assert (
            load_course_references(
                context.user, context.target, ["goal"], reserved=frozenset()
            )
            == {}
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert statements == []


@pytest.mark.parametrize("writer", ["settings", "memory"])
def test_settings_and_memory_adapters_cannot_store_qualified_keys(
    context: SimpleNamespace,
    writer: str,
) -> None:
    from flaskr.service.learn.memory import (
        MemoryUpdate,
        VariableMemoryUpdate,
        stage_memory,
    )
    from flaskr.service.profile.funcs import update_user_profile_with_lable

    before = VariableValue.query.count()
    with unit_of_work():
        if writer == "settings":
            update_user_profile_with_lable(
                context.app,
                context.user,
                [{"key": context.key, "value": "Forged"}],
                course_id=context.target,
            )
        else:
            stage_memory(
                context.app,
                context.user,
                context.target,
                MemoryUpdate(
                    variables=[VariableMemoryUpdate(key=context.key, value="Forged")]
                ),
            )
    assert VariableValue.query.count() == before
    assert (
        get_user_profiles(context.app, context.user, context.target)[context.key]
        == "Source goal"
    )


def test_legacy_formatter_accepts_references_without_accepting_format_expressions() -> (
    None
):
    from flaskr.service.learn.utils_v2 import extract_variables, safe_format_template

    name = "course:" + "a" * 32 + ":goal"
    template = f"{{{{{name}}}}} {{goal}} {{goal:>12}} {{user.name}} {{{{course:invalid:goal}}}}"
    assert set(extract_variables(template)) == {name, "goal"}
    assert safe_format_template(
        template, {name: "Exact", "goal": "Local", "goal:>12": "Bad"}
    ) == ("Exact Local {goal:>12} {user.name} {{course:invalid:goal}}")
