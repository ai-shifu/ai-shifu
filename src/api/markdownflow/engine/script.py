"""Script bundle, script notation detection and variable substitution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import partial
from html import escape
from typing import TYPE_CHECKING, Any

from markdownflow.syntax.variable_names import (
    find_interaction_spans,
    read_interaction_variable,
)

from .marker_context import MarkerContext, analyze_marker_context, marker_syntax_source

# Anything that only makes sense with the MarkdownFlow syntax note.
SYNTAX_RE = re.compile(
    r"(^---[ \t]*$)"  # block separator
    # ?[...] interaction: not escaped by an odd backslash run, not a link.
    r"|(?<!\\)(?:\\\\)*\?\[[^\]\n]*\](?!\()"
    r"|^!?===.*$",  # ===preserved=== / !=== fences
    re.MULTILINE,
)
_FENCE_RE = re.compile(r"(?m)^(`{3,}|~{3,}).*$")


def _closes_fence(line: str, opening: str) -> bool:
    """Report whether this line closes a fence opened with `opening`.

    A fence closes on a line of the same marker, at least as long as the opener, and nothing else.
    Keeping the opening length matters: a ``` line inside a ```` block is content, and closing on
    it would expose the rest of the block to variable substitution and script syntax detection.
    """
    # rstrip, not strip: the opening fences recognized here must start at column 0, so an indented
    # marker is content -- a lesson showing a fenced block inside one would otherwise close early.
    stripped = line.rstrip()
    return len(stripped) >= len(opening) and stripped == opening[0] * len(stripped)


# `%{{name}}` marks a variable this script collects during the lesson, in a question or an
# instruction to remember something.
_LITERAL_SPAN_RE = re.compile(r"(!===.*?!===|(?<!!)===(?!=).*?===)")
_PRESERVED_LINE_RE = re.compile(r"^[ \t]*===(.+?)===[ \t]*$")


if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True)
class ScriptBundle:
    """What the author wrote.

    `script` is the main document, `constraints` an optional global-rules document, and `extras`
    additional named documents such as reference material. A single file is a bundle with only
    `script` set.
    """

    script: str
    constraints: str | None = None
    extras: Mapping[str, str] = field(default_factory=dict)

    def all_text(self) -> str:
        """Join every document in the bundle, for syntax detection."""
        parts = [self.script, self.constraints or "", *self.extras.values()]
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready form of the bundle."""
        return {
            "script": self.script,
            "constraints": self.constraints,
            "extras": dict(self.extras),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ScriptBundle:
        """Rebuild a bundle from its JSON form."""
        return cls(
            script=d["script"],
            constraints=d.get("constraints"),
            extras=dict(d.get("extras") or {}),
        )


def detect_syntax(text: str) -> bool:
    """Report whether the text uses any MarkdownFlow notation outside fenced code blocks."""
    source = _strip_fences(text)
    return bool(SYNTAX_RE.search(source)) or any(
        marker.name is not None for marker in analyze_marker_context(source).markers
    )


def _project_variable_markers(
    text: str, values: Mapping[str, Any] | None = None
) -> tuple[str, dict[str, tuple[str, str | None, bool]], re.Pattern[str]]:
    """Hide opaque marker names while the surrounding Markdown is inspected."""
    marker_prefix = "\x00mdf-variable:"
    while marker_prefix in text or any(
        marker_prefix in str(value) for value in (values or {}).values()
    ):
        marker_prefix += ":"
    markers = {}
    masked: list[str] = []
    at = 0
    context = analyze_marker_context(text, fence_indent=0)
    bindings = _interaction_bindings(text, context)
    for marker in context.markers:
        token = f"{marker_prefix}{len(markers)}\x00"
        markers[token] = (
            text[marker.start : marker.end],
            marker.name,
            marker.start in bindings
            or bool(marker.start and text[marker.start - 1] == "%"),
        )
        masked.extend((text[at : marker.start], token))
        at = marker.end
    masked.append(text[at:])
    return "".join(masked), markers, re.compile(re.escape(marker_prefix) + r"\d+\x00")


def _strip_fences(text: str) -> str:
    projected, markers, tokens = _project_variable_markers(text)
    out: list[str] = []
    in_fence: str | None = None
    for line in projected.splitlines():
        m = _FENCE_RE.match(line)
        if m:
            if in_fence is None:
                in_fence = m.group(1)
            elif _closes_fence(line, in_fence):
                in_fence = None
            continue
        if in_fence is None:
            out.append(line)
    return tokens.sub(lambda match: markers[match.group(0)][0], "\n".join(out))


def _interaction_bindings(text: str, context: MarkerContext) -> set[int]:
    """Locate leading bindings within the existing document control boundaries."""
    bindings: set[int] = set()
    syntax = list(marker_syntax_source(text, context))
    # An unfinished literal example must not consume a later real control's end.
    for opening, closing in context.literals:
        at = text.find("?[", opening, closing)
        while at >= 0:
            syntax[at] = "\x00"
            at = text.find("?[", at + 2, closing)
    literal = 0
    for start, end in find_interaction_spans(text, syntax_source="".join(syntax)):
        while literal < len(context.literals) and context.literals[literal][1] <= start:
            literal += 1
        if literal < len(context.literals) and context.literals[literal][0] <= start:
            continue
        marker = read_interaction_variable(text[start + 2 : end - 1])
        if marker is not None and marker.name is not None:
            bindings.add(start + 2 + marker.start)
    return bindings


def collected_names(text: str) -> frozenset[str]:
    """Return explicit percent declarations and leading interaction bindings.

    Fenced blocks are content the lesson shows, not instructions it follows, so a `%{{name}}`
    inside one is an example of the notation rather than a question. Counted as collected, it
    would drop a real memory value that nothing in the lesson is going to ask for again --
    exactly what a lesson teaching MarkdownFlow would do to itself.
    """
    # Removing fenced examples must not join surrounding text into a new binding.
    context = analyze_marker_context(text)
    bindings = _interaction_bindings(text, context)
    collected = {
        marker.name
        for marker in context.markers
        if marker.name is not None and marker.start in bindings
    }
    source = _strip_fences(text)
    return frozenset(collected) | frozenset(
        marker.name
        for marker in analyze_marker_context(source).markers
        if marker.name is not None and marker.start and source[marker.start - 1] == "%"
    )


def substitution_names(bundle: ScriptBundle) -> frozenset[str]:
    """Name values rendered into host script/constraints, excluding collected answers."""
    return frozenset(
        marker.name
        for text in (bundle.script, bundle.constraints or "")
        for source in (_strip_fences(text),)
        for marker in analyze_marker_context(source).markers
        if marker.name is not None
        and not (marker.start and source[marker.start - 1] == "%")
    ) - collected_names(bundle.script)


def final_preserved_line(text: str) -> str | None:
    """Return a unique inline verbatim line at the script's physical end, if present.

    Fenced examples and repeated author blocks are not a single terminal line. This is a
    narrow display anchor, never evidence that every preceding instruction was completed.
    """
    projected, markers, tokens = _project_variable_markers(text)

    def restore(match: re.Match[str]) -> str:
        return markers[match.group(0)][0]

    lines = projected.rstrip().splitlines()
    if not lines or not (match := _PRESERVED_LINE_RE.fullmatch(lines[-1])):
        return None
    in_fence: str | None = None
    preserved: list[str] = []
    for line in lines:
        if fence := _FENCE_RE.match(line):
            if in_fence is None:
                in_fence = fence.group(1)
            elif _closes_fence(line, in_fence):
                in_fence = None
        elif in_fence is None and (part := _PRESERVED_LINE_RE.fullmatch(line)):
            preserved.append("".join(tokens.sub(restore, part.group(1)).split()))
    content = tokens.sub(restore, match.group(1))
    if in_fence is not None or preserved.count("".join(content.split())) != 1:
        return None
    return content


def substitute_variables(
    text: str,
    values: Mapping[str, Any],
    *,
    collected: frozenset[str] = frozenset(),
    unavailable: bool = False,
) -> str:
    """Replace `{{name}}` with `values[name]` outside fenced code blocks.

    `%{{name}}` and unknown names are left untouched so the model can still see what the author
    meant. Host prompt rendering opts into explicit unavailable-value metadata instead;
    this is request guidance, never a learner fact or a memory write.

    A name in `collected` is left untouched as well, whatever memory holds for it. Those are the
    variables this script is about to ask the learner for, and substitution happens once, before
    the lesson starts. A script that echoes one back -- a line reading "your goal is {{purpose}}"
    placed after the question that fills `purpose` -- would otherwise carry the previous
    session's answer into this one as a statement of fact, and a model given both that statement
    and a fresh tool result believes the statement. One lesson recorded a goal the learner had
    given weeks earlier while they were looking at the "not sure yet" they had just chosen.

    Left as `{{purpose}}`, the model fills it from the answer it was actually given. The 1.0 run
    never had this problem: it rendered each block when it reached it, after the interaction had
    already written the variable.
    """
    # Hide whole markers before Markdown line/literal handling. Their names are opaque;
    # neither a nested opener nor padding that splitlines treats as a line break is syntax.
    projected, markers, tokens = _project_variable_markers(text, values)

    def restore(m: re.Match[str]) -> str:
        return markers[m.group(0)][0]

    def repl(m: re.Match[str], *, literal: bool = False) -> str:
        """Resolve a read without turning missing literal notation into metadata."""
        raw, name, assignment = markers[m.group(0)]
        if name is None or assignment or name in collected:
            return raw
        if name not in values or values[name] in (None, ""):
            return (
                f'<unavailable_learner_value name="{escape(name, quote=True)}" />'
                if unavailable and not literal
                else raw
            )
        v = values[name]
        return ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)

    out: list[str] = []
    in_fence: str | None = None
    in_verbatim = False
    for line in projected.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if m:
            if in_fence is None:
                in_fence = m.group(1)
            elif _closes_fence(line, in_fence):
                in_fence = None
            out.append(tokens.sub(restore, line))
            continue
        if in_fence:
            out.append(tokens.sub(restore, line))
        elif unavailable and line.strip() == "!===":
            in_verbatim = not in_verbatim
            out.append(line)
        elif unavailable and in_verbatim:
            out.append(tokens.sub(partial(repl, literal=True), line))
        elif unavailable:
            # Preserve missing notation inside authored literal spans, while known
            # personalization still follows the pre-existing substitution contract.
            out.append(
                "".join(
                    tokens.sub(partial(repl, literal=bool(index % 2)), part)
                    for index, part in enumerate(_LITERAL_SPAN_RE.split(line))
                )
            )
        else:
            out.append(tokens.sub(repl, line))
    return "".join(out)


def render_memory_section(
    bundle: ScriptBundle,
    memory: Mapping[str, Any],
    *,
    limit: int | None = None,
    priority: frozenset[str] = frozenset(),
) -> tuple[str, bool]:
    """Project whole values into one bounded JSON payload without editing stored memory.

    Referenced and host-priority keys come first; other keys retain input order. A value that
    does not fit is omitted, never shortened.
    """
    collected = collected_names(bundle.script)
    remembered = {k: v for k, v in memory.items() if k not in collected}
    selected = remembered
    if limit is not None:
        if limit < 2:
            message = "memory context limit must fit an empty JSON object"
            raise ValueError(message)
        references = frozenset(
            marker.name
            for text in (bundle.script, bundle.constraints or "")
            for marker in analyze_marker_context(_strip_fences(text)).markers
            if marker.name is not None
        )
        preferred = references | priority
        selected = {}
        for key in sorted(remembered, key=lambda k: k not in preferred):
            candidate = {**selected, key: remembered[key]}
            if len(json.dumps(candidate, ensure_ascii=False, indent=2)) <= limit:
                selected[key] = remembered[key]
    mem = json.dumps(selected, ensure_ascii=False, indent=2)
    section = f"<memory>\n{mem}\n</memory>"
    if len(selected) < len(remembered):
        section += (
            "\n\n<memory_context>Some stored values were omitted to fit the context budget. "
            "An absent key is unknown here, not forgotten or deleted. Do not infer its value. "
            "Use recall for a needed omitted answer when available.</memory_context>"
        )
    return section, len(selected) < len(remembered)


def render_first_prompt(
    bundle: ScriptBundle,
    memory: Mapping[str, Any],
    *,
    memory_limit: int | None = None,
    memory_priority: frozenset[str] = frozenset(),
) -> str:
    """Compose the first user message.

    Learner memory first, followed by the original script, constraints and extras.
    """
    # What this lesson is about to ask for is not something the learner has already said. Shown
    # in memory, an earlier answer is read as the current one -- and a model that has both a
    # stale fact and a fresh tool result tends to trust the fact.
    memory_section = render_memory_section(
        bundle, memory, limit=memory_limit, priority=memory_priority
    )[0]
    return memory_section + "\n\n" + render_script_documents(bundle)


def render_script_documents(bundle: ScriptBundle) -> str:
    """Render the script, constraints and extras part of the first user message."""
    parts = [f"<script>\n{bundle.script}\n</script>"]
    if bundle.constraints:
        parts.append(f"<constraints>\n{bundle.constraints}\n</constraints>")
    for name, body in bundle.extras.items():
        parts.append(f'<extra name="{name}">\n{body}\n</extra>')
    return "\n\n".join(parts)
