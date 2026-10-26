"""Refresh saved native 2.0 prompts using their historical literal rendering."""

import json

import pytest
from flaskr.service.learn.agent.deleted_memory import refresh_deleted_memory
from flaskr.service.learn.agent.legacy_prompt import _render_legacy_text
from flaskr.service.learn.agent.nickname import refresh_nickname
from markdownflow.engine import ScriptBundle, Session, render_first_prompt
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

MEMORY = {"goal": "private goal", "sys_user_nickname": "Before"}
# Fixed outputs from the native 2.0 renderer before question-memory migration.
HISTORICAL_LITERALS = [
    ("Use `{{goal}}` for `{{sys_user_nickname}}`.", "Use `private goal` for `Before`."),
    (
        '<span title="{{goal}}">{{sys_user_nickname}}</span>',
        '<span title="private goal">Before</span>',
    ),
    ("$x {{goal}}$ for {{sys_user_nickname}}", "$x private goal$ for Before"),
    (r"Use \{{goal}} for {{sys_user_nickname}}.", r"Use \{{goal}} for Before."),
    (r"Use \\{{goal}} for {{sys_user_nickname}}.", r"Use \\private goal for Before."),
    (r"Use `\{{goal}}` for {{sys_user_nickname}}.", r"Use `\private goal` for Before."),
    (
        '<span title="\\{{goal}}">{{sys_user_nickname}}</span>',
        '<span title="\\private goal">Before</span>',
    ),
    (
        "```\n{{unclosed\n```\n{{goal}} for {{sys_user_nickname}}.",
        "```\n{{unclosed\n```\nprivate goal for Before.",
    ),
    (
        "`{{unclosed`\n{{goal}} for {{sys_user_nickname}}.",
        "`{{unclosed`\nprivate goal for Before.",
    ),
    (
        "Use `{{goal}}`.\n````markdown\n```\n{{goal}}\n````\n{{sys_user_nickname}}",
        "Use `private goal`.\n````markdown\n```\n{{goal}}\n````\nBefore",
    ),
]


for opening, closing in [
    ("<!--", "-->"),
    ("<?x", "?>"),
    ("<![CDATA[", "]]>"),
    ("<!DOCTYPE", ">"),
]:
    HISTORICAL_LITERALS.append(
        (
            opening
            + "\n{{ unfinished\n"
            + closing
            + " {{goal}} for {{sys_user_nickname}}.",
            opening + "\n{{ unfinished\n" + closing + " private goal for Before.",
        )
    )


@pytest.mark.parametrize(("source", "historical"), HISTORICAL_LITERALS)
@pytest.mark.parametrize("unavailable", [False, True])
def test_historical_renderer_matches_fixed_literal_outputs(
    source: str, historical: str, unavailable: bool
) -> None:
    assert _render_legacy_text(source, MEMORY, unavailable=unavailable) == historical


@pytest.mark.parametrize(("source", "historical"), HISTORICAL_LITERALS)
@pytest.mark.parametrize("action", ["delete", "nickname"])
@pytest.mark.parametrize("legacy", [False, True])
def test_refresh_rewrites_only_the_saved_native_host_sections(
    source: str, historical: str, action: str, legacy: bool
) -> None:
    bundle = ScriptBundle(script=source, constraints=source)
    if legacy:
        prompt = (
            "<memory>\n"
            + json.dumps(MEMORY, ensure_ascii=False, indent=2)
            + f"\n</memory>\n\n<script>\n{historical}\n</script>"
            + f"\n\n<constraints>\n{historical}\n</constraints>"
        )
    else:
        prompt = render_first_prompt(bundle, MEMORY)
    suffix = "\n\nMy question mentions literal {{goal}} and Before."
    evidence = ModelRequest(
        parts=[
            UserPromptPart("The old goal was private goal and nickname Before."),
            ToolReturnPart("remember", {"original": "{{goal}}"}, "original-call"),
        ]
    )
    session = Session(
        script=bundle,
        user_memory=dict(MEMORY),
        initial_memory=dict(MEMORY),
        messages=[ModelRequest(parts=[UserPromptPart(prompt + suffix)]), evidence],
    )
    payload = session.to_dict()
    if legacy:
        payload["initial_variables"] = payload.pop("initial_memory")
    session = Session.from_dict(payload)
    evidence = session.messages[1]
    if action == "delete":
        refresh_deleted_memory(session, frozenset({"goal"}))
        expected_memory = {"sys_user_nickname": "Before"}
    else:
        refresh_nickname(session, {"sys_user_nickname": "After"})
        expected_memory = {**MEMORY, "sys_user_nickname": "After"}
    refreshed = session.messages[0].parts[0].content
    assert (
        json.JSONDecoder().raw_decode(refreshed, len("<memory>\n"))[0]
        == expected_memory
    )
    assert f"<script>\n{source}\n</script>" in refreshed
    assert f"<constraints>\n{source}\n</constraints>" in refreshed
    assert refreshed.endswith(suffix)
    assert session.messages[1] is evidence
    assert session.script == bundle
    if action == "delete":
        assert "private goal" not in refreshed
        assert "goal" not in session.all_memory()


@pytest.mark.parametrize("unavailable", [False, True])
def test_unavailable_historical_inline_value_matches_its_recorded_format(
    unavailable: bool,
) -> None:
    expected = (
        'Use `<unavailable_learner_value name="missing" />`.'
        if unavailable
        else "Use `{{missing}}`."
    )
    assert (
        _render_legacy_text("Use `{{missing}}`.", {}, unavailable=unavailable)
        == expected
    )


@pytest.mark.parametrize("declared_in_main", [False, True])
@pytest.mark.parametrize("action", ["delete", "nickname"])
def test_historical_main_script_declarations_apply_to_both_host_sections(
    declared_in_main: bool, action: str
) -> None:
    main = "Use {{goal}} and {{sys_user_nickname}}."
    brief = "Use {{goal}} for {{sys_user_nickname}}."
    if declared_in_main:
        main = "Remember %{{goal}}. " + main
        old_main = "Remember %{{goal}}. Use {{goal}} and Before."
        old_brief = "Use {{goal}} for Before."
        old_memory = {"sys_user_nickname": "Before"}
    else:
        brief = "Remember %{{goal}}. " + brief
        old_main = "Use private goal and Before."
        old_brief = "Remember %{{goal}}. Use private goal for Before."
        old_memory = dict(MEMORY)
    prompt = (
        "<memory>\n"
        + json.dumps(old_memory, ensure_ascii=False, indent=2)
        + f"\n</memory>\n\n<script>\n{old_main}\n</script>"
        + f"\n\n<constraints>\n{old_brief}\n</constraints>"
    )
    evidence = ModelRequest(
        parts=[UserPromptPart("Keep {{goal}} literal in my question.")]
    )
    session = Session(
        script=ScriptBundle(script=main, constraints=brief),
        user_memory=dict(MEMORY),
        initial_memory=dict(old_memory),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), evidence],
    )
    if action == "delete":
        refresh_deleted_memory(
            session, frozenset({"goal"}), current={"goal": "replacement goal"}
        )
        expected_memory = {"goal": "replacement goal", "sys_user_nickname": "Before"}
    else:
        refresh_nickname(session, {"sys_user_nickname": "After"})
        expected_memory = {**old_memory, "sys_user_nickname": "After"}
    refreshed = session.messages[0].parts[0].content
    assert (
        json.JSONDecoder().raw_decode(refreshed, len("<memory>\n"))[0]
        == expected_memory
    )
    assert f"<script>\n{main}\n</script>" in refreshed
    assert f"<constraints>\n{brief}\n</constraints>" in refreshed
    assert session.messages[1] is evidence


@pytest.mark.parametrize("action", ["delete", "nickname"])
@pytest.mark.parametrize(
    "notice", ["", "\n\n<memory_context>Some values omitted.</memory_context>"]
)
def test_unmatched_script_still_refreshes_the_recognized_memory_envelope(
    action: str, notice: str
) -> None:
    from markdownflow.engine.memory_context import parse_initial_memory_prompt

    original = {**MEMORY, "pace": "slow"}
    untouched = "<script>\nEarlier unknown host source with {{goal}}.\n</script>\n\n<constraints>\nEarlier brief.\n</constraints>\n\nLearner suffix."
    prompt = (
        "<memory>\n"
        + json.dumps(original)
        + "\n</memory>"
        + notice
        + "\n\n"
        + untouched
    )
    later = ModelRequest(
        parts=[
            UserPromptPart("private goal and Before"),
            ToolReturnPart("interact", "private goal", "old-answer"),
        ]
    )
    session = Session(
        script=ScriptBundle(script="Current source.", constraints="Current brief."),
        user_memory=dict(original),
        initial_memory=dict(original),
        messages=[ModelRequest(parts=[UserPromptPart(prompt)]), later],
    )
    if action == "delete":
        refresh_deleted_memory(session, frozenset({"goal"}))
        expected = {"sys_user_nickname": "Before", "pace": "slow"}
    else:
        refresh_nickname(session, {"sys_user_nickname": "After"})
        expected = {**original, "sys_user_nickname": "After"}
    refreshed = session.messages[0].parts[0].content
    parsed = parse_initial_memory_prompt(refreshed)
    assert parsed is not None
    assert parsed.memory == expected
    assert parsed.notice == notice
    assert refreshed[parsed.script_start :] == untouched
    assert session.messages[1] is later
    if action == "delete":
        assert "goal" not in session.initial_memory
    else:
        assert "sys_user_nickname" not in session.initial_memory
    once = session.dumps()
    if action == "delete":
        refresh_deleted_memory(session, frozenset({"goal"}))
    else:
        refresh_nickname(session, {"sys_user_nickname": "After"})
    assert session.dumps() == once
