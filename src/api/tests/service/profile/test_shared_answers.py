"""Exercise explicit cross-course writes against real revisioned database records."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from types import SimpleNamespace

    from flaskr.service.profile.shared_answers import SharedAnswer

import pytest
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.memory import (
    MemoryUpdate,
    VariableMemoryUpdate,
    load_memory,
    stage_memory,
)
from flaskr.service.profile.api import get_global_profile_keys
from flaskr.service.profile.dtos import ProfileToSave
from flaskr.service.profile.funcs import get_user_profiles, save_user_profiles
from flaskr.service.profile.models import Variable, VariableValue
from flaskr.service.profile.shared_answers import (
    load_shared_answers,
    shared_answer_names,
    stage_shared_answers,
)
from flaskr.service.shifu.models import DraftShifu, PublishedOutlineItem, PublishedShifu

from tests.service.profile.test_course_references import (
    _published_text,
    _value,
    context,
)

__all__ = ["context"]


@pytest.fixture
def shared(context: SimpleNamespace) -> SimpleNamespace:
    context.share = f"share:{context.source}:goal"
    context.script = f"Ask ?[%{{{{{context.share}}}}} ...Updated goal]."
    with unit_of_work():
        db.session.add(
            Variable(
                shifu_bid=context.target, key=context.share, variable_bid=uuid4().hex
            )
        )
        db.session.add(
            Variable(shifu_bid=context.source, key="goal", variable_bid=uuid4().hex)
        )
    _published_text(context, context.script)
    return context


def snapshot(c: SimpleNamespace, **overrides: object) -> dict[str, SharedAnswer]:
    args = {
        "user_bid": c.user,
        "course": c.target,
        "names": [c.share],
        "reserved": get_global_profile_keys(),
        "outline_bid": c.outline,
    }
    return load_shared_answers(**(args | overrides))


def source_value(c: SimpleNamespace) -> str:
    return (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.source, key="goal")
        .order_by(VariableValue.id.desc())
        .first()
        .value
    )


def test_explicit_write_updates_original_only_and_reads_refresh(
    shared: SimpleNamespace,
) -> None:
    c = shared
    expected = snapshot(c)
    assert expected[c.share].value == "Source goal"
    exact = 'New goal\n</memory> "' + "é" * 3000
    with unit_of_work():
        assert stage_shared_answers(
            c.app, c.user, c.target, c.outline, {c.share: exact}, expected
        ) == {c.share}
    assert source_value(c) == exact
    assert (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.target).count() == 0
    )
    _published_text(c, c.script + f"\nUse {{{{{c.share}}}}}.")
    assert (
        get_user_profiles(
            c.app, c.user, c.target, reference_text=f"Use {{{{{c.share}}}}}."
        )[c.share]
        == exact
    )
    assert c.share not in get_user_profiles(c.app, c.user, c.target)


@pytest.mark.parametrize(
    "change",
    [
        "source_draft_owner",
        "source_published_owner",
        "target_draft_owner",
        "target_published_owner",
        "source_deleted",
        "target_deleted",
        "source_definition",
        "target_definition",
        "declaration",
        "deleted_outline",
        "source_value",
        "source_tombstone",
    ],
)
def test_authority_and_source_version_are_rechecked_at_write(
    shared: SimpleNamespace, change: str
) -> None:
    c = shared
    expected = snapshot(c)
    assert c.share in expected
    with unit_of_work():
        if change.endswith("owner"):
            model = DraftShifu if "draft" in change else PublishedShifu
            course = c.source if change.startswith("source") else c.target
            db.session.add(model(shifu_bid=course, created_user_bid=uuid4().hex))
        elif change in ("source_deleted", "target_deleted"):
            db.session.add(
                DraftShifu(
                    shifu_bid=c.source if change.startswith("source") else c.target,
                    created_user_bid=c.owner,
                    deleted=1,
                )
            )
        elif change.endswith("definition"):
            Variable.query.filter_by(
                shifu_bid=c.source if change.startswith("source") else c.target,
                key="goal" if change.startswith("source") else c.share,
            ).update({Variable.deleted: 1})
        elif change == "declaration":
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=c.target,
                    outline_item_bid=c.outline,
                    content="No collection now.",
                )
            )
        elif change == "deleted_outline":
            db.session.add(
                PublishedOutlineItem(
                    shifu_bid=c.target,
                    outline_item_bid=c.outline,
                    content=c.script,
                    deleted=1,
                )
            )
        else:
            _value(c, "Concurrent change", deleted=int(change == "source_tombstone"))
    before = source_value(c)
    with unit_of_work():
        assert (
            stage_shared_answers(
                c.app, c.user, c.target, c.outline, {c.share: "Forbidden"}, expected
            )
            == frozenset()
        )
    assert source_value(c) == before


@pytest.mark.parametrize(
    "kind",
    [
        "other_learner",
        "other_outline",
        "no_snapshot",
        "self",
        "system",
        "recursive",
        "malformed",
    ],
)
def test_unguarded_scopes_and_names_never_authorize(
    shared: SimpleNamespace, kind: str
) -> None:
    c = shared
    if kind == "other_learner":
        assert snapshot(c, user_bid=uuid4().hex) == {}
    elif kind == "other_outline":
        assert snapshot(c, outline_bid=uuid4().hex) == {}
    elif kind == "no_snapshot":
        with unit_of_work():
            assert (
                stage_shared_answers(
                    c.app, c.user, c.target, c.outline, {c.share: "Forbidden"}, {}
                )
                == frozenset()
            )
    else:
        name = {
            "self": f"share:{c.target}:goal",
            "system": f"share:{c.source}:sys_user_nickname",
            "recursive": f"share:{c.source}:course:{c.target}:goal",
            "malformed": "share:missing:goal",
        }[kind]
        assert snapshot(c, names=[name]) == {}
    assert source_value(c) == "Source goal"


@pytest.mark.parametrize(
    "wrapper", ["```\n{}\n```", "<!-- {} -->", "~~~\n{}\n~~~", "Use {{{{{name}}}}}."]
)
def test_comments_examples_and_reads_do_not_grant_write_permission(
    shared: SimpleNamespace, wrapper: str
) -> None:
    c = shared
    text = wrapper.format(c.script, name=c.share)
    _published_text(c, text)
    assert snapshot(c) == {}
    assert shared_answer_names(text, collect=True) == frozenset()


def test_profile_settings_and_generic_memory_facade_cannot_bypass_writeback(
    shared: SimpleNamespace,
) -> None:
    c = shared
    with unit_of_work():
        save_user_profiles(
            c.app, c.user, c.target, [ProfileToSave(c.share, "Forbidden", "")]
        )
        patch = MemoryUpdate(
            variables=[VariableMemoryUpdate(key=c.share, value="Forbidden")]
        )
        stage_memory(c.app, c.user, c.target, patch)
        assert patch.variables == []
        db.session.add(
            VariableValue(
                user_bid=c.user, shifu_bid=c.target, key=c.share, value="Spoofed"
            )
        )
    assert source_value(c) == "Source goal"
    assert (
        c.share
        not in load_memory(
            c.app, c.user, c.target, include_course_variables=True
        ).variables
    )


def test_failure_rolls_back_staged_source_update(shared: SimpleNamespace) -> None:
    c = shared
    expected = snapshot(c)

    def fail() -> None:
        with unit_of_work():
            assert stage_shared_answers(
                c.app, c.user, c.target, c.outline, {c.share: "Staged"}, expected
            ) == {c.share}
            assert source_value(c) == "Staged"
            message = "failure"
            raise RuntimeError(message)

    with pytest.raises(RuntimeError, match="failure"):
        fail()
    assert source_value(c) == "Source goal"


def test_authoring_and_runtime_formatting_preserve_qualified_shared_names(
    shared: SimpleNamespace,
) -> None:
    from flaskr.service.learn.utils_v2 import extract_variables, safe_format_template
    from markdown_flow import MarkdownFlow

    c = shared
    assert c.share in MarkdownFlow(c.script).extract_variables()
    assert extract_variables(c.script) == [c.share]
    assert (
        safe_format_template("{{" + c.share + "}}", {c.share: "Exact goal"})
        == "Exact goal"
    )


def test_shared_resolution_bounds_distinct_sources_without_copying_values(
    shared: SimpleNamespace,
) -> None:
    c = shared
    names = [f"share:{c.source}:goal_{index:02}" for index in range(33)]
    with unit_of_work():
        for index, name in enumerate(names):
            key = f"goal_{index:02}"
            db.session.add_all(
                [
                    Variable(shifu_bid=c.target, key=name),
                    Variable(shifu_bid=c.source, key=key),
                    VariableValue(
                        user_bid=c.user, shifu_bid=c.source, key=key, value=str(index)
                    ),
                ]
            )
    _published_text(c, "\n".join("Collect %{{" + name + "}}." for name in names))
    result = snapshot(c, names=names)
    assert list(result) == names[:32]
    assert (
        VariableValue.query.filter_by(user_bid=c.user, shifu_bid=c.target).count() == 0
    )
