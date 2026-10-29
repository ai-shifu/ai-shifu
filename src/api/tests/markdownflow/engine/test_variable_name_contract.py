"""Keep existing question-style keys intact across the lesson parser boundaries."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from flaskr.service.learn.agent.interaction_syntax import InteractionSyntaxFilter
from flaskr.service.learn.agent.legacy_protocol import render_interaction
from markdown_flow import InteractionParser, MarkdownFlow
from markdown_flow.parser.variable import replace_variables_in_text
from markdownflow.engine import (
    Engine,
    ErrorEvent,
    InteractionResponseTurn,
    MemoryUpdated,
    Session,
    collected_names,
    marker_context,
    substitute_variables,
)
from markdownflow.engine.events import InteractionRequest
from markdownflow.engine.interaction import InteractionSpec, Option
from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.script import final_preserved_line
from markdownflow.engine.tools import _script_questions
from markdownflow.syntax.variable_names import (
    find_variable_markers,
    format_variable_assignment,
    format_variable_reference,
    normalize_variable_name,
    read_variable_marker,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

pytestmark = pytest.mark.anyio

QUESTION_KEYS = (
    "你的性别是？",
    "gender?",
    "What_is_your_gender?",
    "职业:学生/在职",
    "choice|origin//raw...?",
    "gender_(self)",
    "学习目标_😀？",
    "name",
    "中文变量",
    "\ufeffgender?",
    "gender?\ufeff",
    "\ufeff",
    "What is your gender?",
    "user  name",
    "Which [path] | level//hint...?",
    "a{b",
    "a}b",
    "a}",
    "}",
    "outer{{inner",
    'a"quoted\\path',
)
CHOICES = ("男", "女", "秘密")


def _question(key: str, padding: str = " ") -> str:
    """Use the author's original choice syntax without normalizing its key."""
    if not padding and key.endswith("}"):
        padding = " "
    return f"?[%{{{{{padding}{key}{padding}}}}} {' | '.join(CHOICES)}]"


@pytest.mark.parametrize("key", QUESTION_KEYS)
@pytest.mark.parametrize("padding", ["", " \t"])
def test_existing_question_keys_agree_across_parser_boundaries(
    key: str, padding: str
) -> None:
    """Punctuation in a name cannot become an option delimiter or disappear."""
    authored = _question(key, padding)
    parsed = InteractionParser().parse(authored)
    assert parsed["variable"] == key
    assert [(button["display"], button["value"]) for button in parsed["buttons"]] == [
        (choice, choice) for choice in CHOICES
    ]
    assert MarkdownFlow(authored).extract_variables() == [key]
    assert collected_names(authored) == frozenset({key})

    reference = format_variable_reference(key)
    assert replace_variables_in_text(reference, {key: "女"}, add_quotes=False) == "女"
    assert substitute_variables(reference, {key: "女"}) == "女"
    assert substitute_variables(authored, {key: "女"}) == authored

    questions = _script_questions(authored)
    assert len(questions) == 1
    assert questions[0].variable == key
    assert [choice.strip() for choice in questions[0].choices] == list(CHOICES)
    assert not questions[0].text

    syntax = InteractionSyntaxFilter()
    assert (
        "".join(syntax.feed(character) for character in authored) + syntax.flush() == ""
    )
    assert syntax.spans == [authored]

    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        options=[Option(display=choice) for choice in CHOICES],
        variable=key,
    )
    rendered = render_interaction(spec)
    assert rendered == _question(key)
    assert InteractionParser().parse(rendered)["variable"] == key


@pytest.mark.parametrize("key", QUESTION_KEYS)
async def test_named_question_answer_survives_session_and_wire_round_trips(
    key: str,
) -> None:
    """Exercise admission, deferred tools and returned memory with the exact authored key."""
    calls = 0

    async def model(
        _messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {
                0: DeltaToolCall(
                    name="interact",
                    tool_call_id="question",
                    json_args=json.dumps(
                        {
                            "type": "single",
                            "prompt": "Choose one",
                            "variable": f"\u0085{key}\u001f",
                            "options": [{"display": choice} for choice in CHOICES],
                        }
                    ),
                )
            }
        else:
            yield {
                0: DeltaToolCall(
                    name="finish",
                    tool_call_id="finished",
                    json_args=json.dumps({"summary": "Done"}),
                )
            }

    engine = Engine(FunctionModel(stream_function=model), memory_admission=True)
    session = await engine.new_session(_question(key))
    first = [event async for event in engine.run_turn(session)]
    assert not [event for event in first if isinstance(event, ErrorEvent)]
    request = next(event for event in first if isinstance(event, InteractionRequest))
    assert request.spec.variable == key
    assert render_interaction(request.spec) == _question(key)
    assert first[-1].reason == "interaction"

    session = Session.loads(session.dumps())
    assert session.pending[0].spec.variable == key
    second = [
        event
        async for event in engine.run_turn(
            session, InteractionResponseTurn(values=["女"])
        )
    ]
    assert not [event for event in second if isinstance(event, ErrorEvent)]
    assert [
        (event.key, event.value, event.source)
        for event in second
        if isinstance(event, MemoryUpdated)
    ] == [(key, "女", "interaction")]
    assert second[-1].reason == "finished"
    restored = Session.loads(session.dumps())
    assert restored.memory == {key: "女"}
    assert substitute_variables(format_variable_reference(key), restored.memory) == "女"


@pytest.mark.parametrize(
    "key",
    [
        "a\tb",
        "a\nb",
        "a\u0085b",
        "a\u001cb",
        "a\u001db",
        "a\u001eb",
        "a\u001fb",
    ],
)
def test_engine_does_not_declare_keys_with_internal_controls(
    key: str,
) -> None:
    """Controls inside a normalized key cannot become a stored learner fact."""
    assert collected_names(_question(key)) == frozenset()
    reference = f"{{{{{key}}}}}"
    assert substitute_variables(reference, {key: "女"}) == reference


CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures/variable-name-contract.json").read_text()
)


@pytest.mark.parametrize("case", CONTRACT["normalization"])
def test_shared_normalization_corpus(case: dict) -> None:
    assert normalize_variable_name(case["raw"]) == case["name"]
    formatted = format_variable_reference(case["raw"])
    assert (formatted is None) == (case["name"] is None)
    if formatted is not None:
        marker = read_variable_marker(formatted)
        assert marker is not None
        assert marker.name == case["name"]
        assert substitute_variables(formatted, {case["name"]: "answer"}) == "answer"


@pytest.mark.parametrize("case", CONTRACT["extraction"])
def test_shared_non_recursive_marker_corpus(case: dict) -> None:
    assert (
        list(
            dict.fromkeys(
                marker.name
                for marker in find_variable_markers(case["source"])
                if marker.name is not None
            )
        )
        == case["names"]
    )
    assert MarkdownFlow(case["source"]).extract_variables() == sorted(case["names"])


@pytest.mark.parametrize("case", CONTRACT["interactions"])
def test_shared_interaction_corpus(case: dict) -> None:
    parsed = InteractionParser().parse(case["source"])
    assert parsed["variable"] == case["name"]
    questions = _script_questions(case["source"])
    assert len(questions) == 1
    assert questions[0].variable == case["name"]
    assert collected_names(case["source"]) == frozenset({case["name"]})
    assert format_variable_assignment(case["name"]) in case["source"]


@pytest.mark.parametrize("padding", ["\u0085", "\u001c", "\u001d", "\u001e", "\u001f"])
def test_assignment_extraction_trims_python_only_whitespace(padding: str) -> None:
    """Python padding includes controls absent from JavaScript's whitespace set."""
    key = "你的性别是？"
    authored = _question(key, padding)
    assert collected_names(authored) == frozenset({key})
    assert InteractionParser().parse(authored)["variable"] == key
    assert MarkdownFlow(authored).extract_variables() == [key]


def test_marker_names_are_opaque_to_markdown_and_invalid_outer_markers_are_not_reparsed() -> (
    None
):
    source = "%{{\n```\n}}"
    assert collected_names(source) == frozenset({"```"})
    assert substitute_variables("{{\n```\n}}", {"```": "value"}) == "value"
    assert (
        substitute_variables(
            "{{ a===b===c }}", {"a===b===c": "value"}, unavailable=True
        )
        == "value"
    )
    assert (
        substitute_variables(
            "{{bad\n{{inner}} {{valid}}", {"inner": "wrong", "valid": "right"}
        )
        == "{{bad\n{{inner}} right"
    )


@pytest.mark.parametrize("case", CONTRACT["boundary_cases"])
def test_shared_atomic_interaction_boundary_corpus(case: dict) -> None:
    source = case["source"]
    questions = _script_questions(source)
    assert len(questions) == case["interaction_count"]
    if questions:
        assert questions[0].variable == case["name"]
        assert not questions[0].text
    for cut in range(len(source) + 1):
        syntax = InteractionSyntaxFilter()
        shown = syntax.feed(source[:cut]) + syntax.feed(source[cut:]) + syntax.flush()
        assert len(syntax.spans) == case["interaction_count"]
        assert shown == ("" if case["interaction_count"] else source)


def test_multiline_marker_padding_keeps_one_trimmed_key_across_host_boundaries() -> (
    None
):
    reference = "{{\n name \n}}"
    assignment = "%" + reference
    source = "?[" + assignment + " 男 | 女 | 秘密]"
    assert collected_names(assignment) == frozenset({"name"})
    assert substitute_variables(reference, {"name": "女"}) == "女"
    assert substitute_variables(assignment, {"name": "女"}) == assignment
    assert MarkdownFlow(source).extract_variables() == ["name"]
    assert len(MarkdownFlow(source).get_all_blocks()) == 1
    assert InteractionParser().parse(source)["variable"] == "name"
    assert _script_questions(source)[0].variable == "name"
    spec = InteractionSpec(
        type="single",
        prompt="Choose one",
        variable="name",
        options=[Option(display=value) for value in CHOICES],
    )
    assert InteractionParser().parse(render_interaction(spec))["variable"] == "name"
    for cut in range(len(source) + 1):
        syntax = InteractionSyntaxFilter()
        assert (
            syntax.feed(source[:cut]) + syntax.feed(source[cut:]) + syntax.flush() == ""
        )
        assert syntax.spans == [source]


@pytest.mark.parametrize(
    "prefix",
    [
        "{{\n```key\n}} ",
        "%{{\n~~~key\n}} ",
        "{{bad\x00\n```key\n}} ",
        "{{\n```key\n",  # An unclosed marker claims the remaining tail.
    ],
)
def test_streaming_fences_inside_opaque_markers_have_no_markdown_meaning(
    prefix: str,
) -> None:
    question = "?[甲 | 乙]"
    source = prefix + question
    expected = [] if "}}" not in prefix else [question]
    shown = source if not expected else prefix
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        assert "".join(syntax.feed(part) for part in stream) + syntax.flush() == shown
        assert syntax.spans == expected


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_markers_in_existing_code_fences_do_not_hide_the_real_closing_fence(
    fence: str,
) -> None:
    example = fence + "\n{{ never closed\n?[example]\n" + fence + "\n"
    question = "?[甲 | 乙]"
    source = example + question
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        assert "".join(syntax.feed(part) for part in stream) + syntax.flush() == example
        assert syntax.spans == [question]


@pytest.mark.parametrize("key", ["```key", "~~~key", "===The end==="])
def test_opaque_marker_contents_do_not_hide_or_duplicate_the_final_preserved_line(
    key: str,
) -> None:
    source = "{{\n" + key + "\n}}\n===The end==="
    assert final_preserved_line(source) == "The end"


def test_final_preserved_line_restores_marker_contents_and_keeps_uniqueness() -> None:
    line = "===Result: {{\n a===b===c\n}}==="
    assert final_preserved_line(line) == "Result: {{\n a===b===c\n}}"
    assert final_preserved_line(line + "\n" + line) is None


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_final_preserved_line_ignores_code_and_unclosed_marker_tails(
    fence: str,
) -> None:
    source = fence + "\n{{ never closed\n===The end===\n" + fence
    assert final_preserved_line(source) is None
    assert final_preserved_line(source + "\n===The end===") == "The end"
    assert final_preserved_line("{{ never closed\n===The end===") is None


@pytest.mark.parametrize(
    ("prefix", "captures_question"),
    [
        ("`{{`\n", True),
        ("Prefix `{{`\n", True),
        ("``literal ` {{``\n", True),
        ("`prefix\n{{`\n", True),
        ("\\{{\n", True),
        ("\\\\\\{{\n", True),
        ("{{\n", False),
        ("\\\\{{\n", False),
        ("`unmatched {{\n", False),
        ("\\`{{\n", False),
        ("{{ key\\{{?[inner] }}\n", True),
    ],
)
def test_code_and_escaped_marker_examples_do_not_claim_external_structures(
    prefix: str, captures_question: bool
) -> None:
    example = prefix + "```js\ncode\n```\n"
    question = "?[甲 | 乙]"
    source = example + question
    questions = _script_questions(source)
    assert len(questions) == int(captures_question)
    if questions:
        assert [choice.strip() for choice in questions[0].choices] == ["甲", "乙"]
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        assert "".join(syntax.feed(part) for part in stream) + syntax.flush() == (
            example if captures_question else source
        )
        assert syntax.spans == ([question] if captures_question else [])


@pytest.mark.parametrize(
    "boundary",
    [
        "\n\n",
        "\n \t\n",
        "\r\n\r\n",
        "\n```text\nexample\n```\n",
        "\n~~~\nexample\n~~~\n",
    ],
)
@pytest.mark.parametrize("ticks", ["`", "``"])
def test_unmatched_inline_code_cannot_pair_across_a_paragraph_or_fence(
    boundary: str, ticks: str
) -> None:
    """A later tick cannot turn an active outer marker into a code example."""
    source = f"Show {ticks}{{{{{boundary}{ticks} then ?[%{{{{ q }}}} A|B]"
    assert collected_names(source) == frozenset()
    assert substitute_variables(source, {"q": "wrong"}) == source
    assert _script_questions(source) == []
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        assert "".join(syntax.feed(part) for part in stream) + syntax.flush() == source
        assert syntax.spans == []


@pytest.mark.parametrize("case", CONTRACT["document_context_cases"])
def test_document_literal_boundaries_preserve_collection_and_external_interactions(
    case: dict,
) -> None:
    source = case["source"]
    assert (
        sorted(
            marker.name
            for marker in analyze_marker_context(source).markers
            if marker.name is not None
        )
        == case["names"]
    )
    assert collected_names(source) == frozenset(case["collected"])
    questions = _script_questions(source)
    assert len(questions) == case["interaction_count"]
    assert questions[0].variable == case["name"]
    assert [choice.strip() for choice in questions[0].choices] == case["buttons"]

    question_start = source.rfind("?[")
    question = source[question_start:]
    chunks = [[source], list(source)] + [
        [source[:cut], source[cut:]] for cut in range(len(source) + 1)
    ]
    for stream in chunks:
        syntax = InteractionSyntaxFilter()
        assert (
            "".join(syntax.feed(part) for part in stream) + syntax.flush()
            == source[:question_start]
        )
        assert syntax.spans == [question]

    references = " ".join(format_variable_reference(name) for name in case["names"])
    values = {name: f"value-{index}" for index, name in enumerate(case["names"])}
    assert substitute_variables(source + "\n" + references, values).endswith(
        "\n" + " ".join(values.values())
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Show `{{ q }}` then {{ q }}", "Show `value` then value"),
        ('<span title="{{ q }}"> {{ q }}', '<span title="value"> value'),
        ("Show \\{{ q }} then {{ q }}", "Show \\{{ q }} then value"),
    ],
)
def test_literal_references_keep_old_substitution_and_escaped_openers_stay_literal(
    source: str, expected: str
) -> None:
    assert substitute_variables(source, {"q": "value"}) == expected


@pytest.mark.parametrize(
    ("opening", "suffix"),
    [
        ("<!--", " > {{ q }}"),
        ("<?", " > {{ q }}"),
        ("<![CDATA[", " > {{ q }}"),
        ("<!A", " {{ q }}"),
    ],
)
def test_unclosed_html_candidates_do_not_repeatedly_scan_the_document_tail(
    opening: str, suffix: str
) -> None:
    source = opening * 4096 + suffix
    with patch.object(
        marker_context, "_INLINE_HTML", wraps=marker_context._INLINE_HTML
    ) as native_html:
        context = analyze_marker_context(source)
    assert [marker.name for marker in context.markers] == ["q"]
    # Bound failed native work rather than asserting machine-dependent timings.
    assert native_html.match.call_count <= 1


@pytest.mark.parametrize(
    "html",
    ["<!-->", "<!--->", "<!-- {{ q }} -->", "<? {{ q }} ?>", "<![CDATA[{{ q }}]]>"],
)
def test_html_tail_preflight_preserves_complete_native_literals(html: str) -> None:
    source = "Text " + html + " {{ outside }}"
    context = analyze_marker_context(source)
    assert context.literals == [(5, 5 + len(html))]
    expected = ["q", "outside"] if "{{ q }}" in html else ["outside"]
    assert [marker.name for marker in context.markers] == expected
