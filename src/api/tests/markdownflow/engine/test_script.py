"""Script bundling: variable substitution, script syntax detection, prompt assembly."""

import pytest
from markdownflow.engine import (
    ScriptBundle,
    collected_names,
    detect_syntax,
    render_first_prompt,
    substitute_variables,
)
from markdownflow.engine.script import substitution_names
from markdownflow.engine.tools import script_options


def test_detects_each_syntax_marker() -> None:
    assert detect_syntax("intro\n---\nnext")
    assert detect_syntax("ask ?[%{{x}} A | B]")
    assert detect_syntax("hello {{name}}")
    assert detect_syntax("keep %{{name}}")
    assert detect_syntax("===verbatim===")
    assert detect_syntax("!===\nblock\n!===")


def test_plain_prose_has_no_syntax_markers() -> None:
    assert not detect_syntax(
        "Greet the learner. Ask how they feel. Offer three options."
    )
    assert not detect_syntax("a link ?[text](http://x) is not an interaction")
    assert not detect_syntax("escaped \\?[not one]")


def test_markers_inside_code_fences_are_ignored() -> None:
    assert not detect_syntax("```\n---\n?[x|y]\n{{v}}\n```\nprose")


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
    assert "Say hi to {{name}}" in p
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


@pytest.mark.parametrize("fence", ["```", "~~~~"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r", "\x85", "\u2028"])
@pytest.mark.parametrize(
    "example",
    ["{{unclosed", "%{{unclosed", "<!-- {{unclosed -->", "<!-- %{{unclosed -->"],
)
def test_unclosed_code_example_cannot_capture_markers_after_its_fence(
    fence: str, newline: str, example: str
) -> None:
    """An example's opener cannot hide the closing fence or consume real course keys."""
    before = f"{fence}{newline}{example}{newline}{fence}{newline}Outside "
    text = before + "{{name}} %{{answer}}"

    assert substitution_names(ScriptBundle(script=text)) == frozenset({"name"})
    assert collected_names(text) == frozenset({"answer"})
    assert substitute_variables(text, {"name": "Ada", "answer": "old"}) == (
        before + "Ada %{{answer}}"
    )


def test_marker_outside_code_keeps_fence_and_comment_text_inside_its_name() -> None:
    """Only a real outer fence wins; an opaque key's punctuation remains ordinary text."""
    text = "{{\n```\n}} {{ <!-- key --> }} %{{\n~~~\n}}"

    assert substitution_names(ScriptBundle(script=text)) == frozenset(
        {"```", "<!-- key -->"}
    )
    assert collected_names(text) == frozenset({"~~~"})
    assert (
        substitute_variables(
            text, {"```": "fence", "<!-- key -->": "comment", "~~~": "old"}
        )
        == "fence comment %{{\n~~~\n}}"
    )


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


def test_a_marker_inside_a_fenced_block_is_an_example_not_a_question() -> None:
    """A lesson teaching MarkdownFlow shows the notation; it is not asking anything.

    Counted as collected, the fenced example would drop a real memory value that nothing in the
    lesson asks for again -- the lesson would erase the learner's own answer by quoting syntax.
    """
    text = "greet {{nickname}}\n```\n?[%{{nickname}} A | B]\n```\n"

    assert collected_names(text) == frozenset()
    assert (
        substitute_variables(
            text, {"nickname": "Lin"}, collected=collected_names(text)
        ).splitlines()[0]
        == "greet Lin"
    )


def test_a_marker_outside_a_fence_is_still_collected_when_one_is_present() -> None:
    text = "?[%{{purpose}} A | B]\n```\n?[%{{nickname}} X]\n```\n"

    assert collected_names(text) == frozenset({"purpose"})


@pytest.mark.parametrize("prefix", ["%", ""])
@pytest.mark.parametrize(
    "key", ["goal", "Which [path] | level//hint...?", "outer{{inner", "a}"]
)
def test_interaction_binding_is_collected_and_never_substituted(
    prefix: str, key: str
) -> None:
    marker = prefix + "{{ " + key + " }}"
    source = "?[ " + marker + " A | ...Your goal?]\nThen discuss {{ " + key + " }}."
    bundle = ScriptBundle(script=source)

    assert collected_names(source) == frozenset({key})
    assert substitution_names(bundle) == frozenset()
    assert marker in substitute_variables(source, {key: "stale"})
    assert "stale" not in render_first_prompt(bundle, {key: "stale"})
    assert marker in substitute_variables(source, {}, unavailable=True)
    assert (
        substitute_variables(
            source, {}, collected=collected_names(source), unavailable=True
        )
        == source
    )


@pytest.mark.parametrize(
    "source",
    [
        "Read {{goal}}.",
        "?[Continue {{goal}}]",
        "\\?[{{goal}} A | B]",
        "`?[{{goal}} A | B]`",
        "```md\n?[{{goal}} A | B]\n```",
        "<!-- ?[{{goal}} A | B] -->",
        "?[{{goal}} A | B](https://example.com)",
        "?[{{ }} A | B]",
        "?[{{bad\x00key}} A | B]",
    ],
)
def test_only_valid_leading_interaction_bindings_grant_collection(source: str) -> None:
    assert collected_names(source) == frozenset()


@pytest.mark.parametrize(
    "image",
    [
        "![?[{{goal}} A | B]](url)",
        "[![?[{{goal}} A | B]](url)](outer)",
        "![?[{{goal}} A | B]][image]\n\n[image]: url",
        "> ![?[{{goal}} A | B]][IMAGE]\n>\n> [image]: url",
        "![?[{{goal}} A | B]][two words]\n\n[two  words]: url",
    ],
)
def test_real_image_alt_controls_do_not_declare_bare_bindings(image: str) -> None:
    source = image + "\n\nRead {{goal}}."
    assert collected_names(source) == frozenset()
    assert substitution_names(ScriptBundle(script=source)) == frozenset({"goal"})
    assert "{{goal}}" not in substitute_variables(source, {"goal": "current"})
    assert script_options(source + "\n\n?[{{visible}} C | D]") == {
        "C": "C",
        "D": "D",
    }
    assert collected_names(image.replace("{{goal}}", "%{{goal}}")) == frozenset(
        {"goal"}
    )


@pytest.mark.parametrize(
    "source",
    [
        "![ ?[{{goal}} A | B]",
        "![?[{{goal}} A | B]][missing]",
        "![?[{{goal}} A | B]](unfinished",
        "[?[{{goal}} A | B]](url)",
        "?[{{goal}} A | B] after ![image](url)",
    ],
)
def test_visible_controls_in_unfinished_images_and_link_labels_still_bind(
    source: str,
) -> None:
    assert collected_names(source) == frozenset({"goal"})
    assert "{{goal}}" in substitute_variables(source, {"goal": "stale"})
