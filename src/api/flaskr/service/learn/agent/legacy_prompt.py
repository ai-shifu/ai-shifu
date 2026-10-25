"""Recognize historical expanded host sections during one-way prompt migration.

Only matching old stored prompts uses this renderer. New prompts always carry
literal authored source and learner values exclusively in structured memory.
"""

from __future__ import annotations

import re
from functools import partial
from html import escape
from typing import TYPE_CHECKING, Any

from markdownflow.engine.marker_context import analyze_marker_context
from markdownflow.engine.questions import find_question_markers

if TYPE_CHECKING:
    from collections.abc import Mapping

_FENCE_RE = re.compile(r"(?m)^(`{3,}|~{3,}).*$")
_LITERAL_SPAN_RE = re.compile(r"(!===.*?!===|(?<!!)===(?!=).*?===)")


def _closes_fence(line: str, opening: str) -> bool:
    """Report whether this line closes a fence opened with `opening`.

    A fence closes on a line of the same marker, at least as long as the opener, and nothing else.
    Keeping the opening length matters: a ``` line inside a ```` block is content, and closing on
    it would expose the rest of the block to variable substitution and 1.0 syntax detection.
    """
    # rstrip, not strip: the opening fences recognized here must start at column 0, so an indented
    # marker is content -- a lesson showing a fenced block inside one would otherwise close early.
    stripped = line.rstrip()
    return len(stripped) >= len(opening) and stripped == opening[0] * len(stripped)


def _project_legacy_markers(
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
    for marker in find_question_markers(text):
        if marker.start and text[marker.start - 1] == "\\":
            continue
        token = f"{marker_prefix}{len(markers)}\x00"
        markers[token] = (
            text[marker.start : marker.end],
            marker.name,
            bool(marker.start and text[marker.start - 1] == "%"),
        )
        masked.extend((text[at : marker.start], token))
        at = marker.end
    masked.append(text[at:])
    projected = "".join(masked)
    tokens = re.compile(re.escape(marker_prefix) + r"\d+\x00")
    # Legacy references are found lexically before asking today's scanner only
    # for Markdown literal boundaries. Standalone braces have no new semantics.
    literal_spans = analyze_marker_context(projected, fence_indent=0).literals
    projected = tokens.sub(
        lambda match: (
            markers[match.group(0)][0]
            if any(start <= match.start() < end for start, end in literal_spans)
            else match.group(0)
        ),
        projected,
    )
    return projected, markers, tokens


def _render_legacy_text(
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
    projected, markers, tokens = _project_legacy_markers(text, values)

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


def matched_section_length(
    content: str,
    start: int,
    tag: str,
    source: str,
    memory: Mapping[str, Any],
    collected: frozenset[str],
) -> int | None:
    """Find only exact known literal or historical host sections at this offset."""
    candidates = [
        source,
        *(
            _render_legacy_text(
                source, memory, collected=collected, unavailable=unavailable
            )
            for unavailable in (True, False)
        ),
    ]
    for candidate in candidates:
        section = f"<{tag}>\n{candidate}\n</{tag}>"
        if content.startswith(section, start):
            return len(section)
    return None
