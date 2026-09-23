"""Script bundling: variable substitution, 1.0 syntax detection, prompt assembly."""

from flaskr.service.learn.agent.engine import (
    ScriptBundle,
    collected_names,
    detect_v1_syntax,
    render_first_prompt,
    substitute_variables,
)


def test_detects_each_v1_marker() -> None:
    assert detect_v1_syntax("intro\n---\nnext")
    assert detect_v1_syntax("ask ?[%{{x}} A | B]")
    assert detect_v1_syntax("hello {{name}}")
    assert detect_v1_syntax("keep %{{name}}")
    assert detect_v1_syntax("===verbatim===")
    assert detect_v1_syntax("!===\nblock\n!===")


def test_plain_prose_is_not_v1() -> None:
    assert not detect_v1_syntax(
        "Greet the learner. Ask how they feel. Offer three options."
    )
    assert not detect_v1_syntax("a link ?[text](http://x) is not an interaction")
    assert not detect_v1_syntax("escaped \\?[not one]")


def test_markers_inside_code_fences_are_ignored() -> None:
    assert not detect_v1_syntax("```\n---\n?[x|y]\n{{v}}\n```\nprose")


def test_substitute_replaces_known_and_keeps_unknown_and_preserved() -> None:
    out = substitute_variables(
        "Hi {{name}}, {{missing}} and %{{name}} and {{ name }}", {"name": "Lin"}
    )
    assert out == "Hi Lin, {{missing}} and %{{name}} and Lin"


def test_substitute_list_and_fence() -> None:
    out = substitute_variables("picks: {{p}}\n```\n{{p}}\n```\n", {"p": ["a", "b"]})
    assert out == "picks: a, b\n```\n{{p}}\n```\n"


def test_first_prompt_layout() -> None:
    b = ScriptBundle(
        script="Say hi to {{name}}", constraints="Be brief", extras={"ref": "R"}
    )
    p = render_first_prompt(b, {"name": "Lin"})
    assert (
        p.index("<memory>")
        < p.index("<script>")
        < p.index("<constraints>")
        < p.index('<extra name="ref">')
    )
    assert "Say hi to Lin" in p
    assert '"name": "Lin"' in p


def test_bundle_roundtrip() -> None:
    b = ScriptBundle(script="s", constraints=None, extras={"a": "1"})
    assert ScriptBundle.from_dict(b.to_dict()) == b


def test_a_longer_fence_is_not_closed_by_a_shorter_one_inside_it() -> None:
    """A ``` line inside a ```` block is content, so the block must stay open across it."""
    text = "````markdown\n```\n{{name}}\n```\n````\n{{name}}\n"
    out = substitute_variables(text, {"name": "Ada"})
    assert out.count("{{name}}") == 1  # the one inside the fence survives
    assert out.endswith("Ada\n")


def test_a_closing_fence_carries_nothing_else() -> None:
    """`\u0060\u0060\u0060python` opens a block; only a bare marker line closes it."""
    text = "```\n{{name}}\n``` trailing words\n{{name}}\n```\n{{name}}\n"
    out = substitute_variables(text, {"name": "Ada"})
    assert out.count("{{name}}") == 2  # both lines inside the block are untouched


def test_an_indented_marker_does_not_close_a_fence() -> None:
    """Openings must start at column 0, so an indented marker inside a block is content.

    A lesson that teaches fenced code blocks contains exactly this.
    """
    text = "```markdown\n    ```\n{{name}}\n```\n{{name}}\n"
    out = substitute_variables(text, {"name": "Ada"})
    assert out.count("{{name}}") == 1  # the one inside the block survives
    assert out.endswith("Ada\n")


# --- a variable this lesson collects ------------------------------------------------------

_ECHOES_ITS_OWN_ANSWER = (
    "- ask the learner why they are here\n"
    "\n"
    "?[%{{purpose}} not sure yet | ...why are you learning AI?]\n"
    "\n"
    "the learner's goal: {{purpose}}\n"
    "- comment on whether that goal is realistic\n"
)


def test_a_variable_the_script_collects_is_not_filled_from_an_earlier_session() -> None:
    """The script states the goal *after* asking for it, so a stale value reads as this run's.

    A learner who chose "not sure yet" had a goal from weeks earlier recorded and read back to
    them: the model was given the old answer as a statement in the script and believed it over
    the tool result it had just received.
    """
    out = substitute_variables(
        _ECHOES_ITS_OWN_ANSWER,
        {"purpose": "find me a girlfriend"},
        collected=collected_names(_ECHOES_ITS_OWN_ANSWER),
    )

    assert "find me a girlfriend" not in out
    assert "the learner's goal: {{purpose}}" in out


def test_a_variable_the_script_only_reads_is_still_filled() -> None:
    """Nothing in the script asks for it, so memory is the only place it can come from."""
    text = "greet {{nickname}} warmly\n"

    out = substitute_variables(
        text, {"nickname": "Lin"}, collected=collected_names(text)
    )

    assert out == "greet Lin warmly\n"


def test_the_memory_block_drops_what_this_lesson_will_ask_for() -> None:
    """Left in, an earlier answer is read as the current one even when the script no longer says so."""
    bundle = ScriptBundle(script=_ECHOES_ITS_OWN_ANSWER)

    prompt = render_first_prompt(
        bundle, {"purpose": "find me a girlfriend", "nickname": "Lin"}
    )

    assert "find me a girlfriend" not in prompt
    assert '"nickname": "Lin"' in prompt


def test_a_collected_name_is_recognised_wherever_the_script_names_it() -> None:
    assert collected_names("?[%{{a}} x | y]\n- remember %{{ b }}\n") == frozenset(
        {"a", "b"}
    )
    assert collected_names("just {{c}} here\n") == frozenset()
