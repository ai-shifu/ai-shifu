"""Script bundling: variable substitution, 1.0 syntax detection, prompt assembly."""

from flaskr.service.learn.agent.engine import (
    ScriptBundle,
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
