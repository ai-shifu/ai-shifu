"""Recognize historical expanded host sections during one-way prompt migration.

Only matching old stored prompts uses this renderer. New prompts always carry
literal authored source and learner values exclusively in structured memory.
"""

from __future__ import annotations

import re
from functools import partial
from html import escape
from typing import TYPE_CHECKING, Any

from markdownflow.engine.document_blocks import DocumentBlocks
from markdownflow.engine.marker_context import _INLINE_HTML, analyze_marker_context
from markdownflow.engine.questions import read_question_marker

if TYPE_CHECKING:
    from collections.abc import Mapping

    from markdownflow.engine.script import ScriptBundle

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
    literal_spans = []
    blocks = DocumentBlocks(text, _INLINE_HTML)
    for start, end in analyze_marker_context(text, fence_indent=0).literals:
        html = blocks.terminated_html(start)
        if html is not None and start < html.opening_end < end:
            # The former scanner separated a terminated HTML token from the
            # remainder of its closing line; an unfinished example cannot own it.
            literal_spans.extend(((start, html.opening_end), (html.opening_end, end)))
        else:
            literal_spans.append((start, end))
    # A code example cannot make its unfinished opener consume a later reference.
    # Walk native fence lines before reading opaque historical names.
    line_ends = {}
    offset = 0
    for line in text.splitlines(keepends=True):
        line_ends[offset] = offset + len(line)
        offset += len(line)
    at = 0
    accepted_ranges: list[tuple[int, int]] = []
    position = 0
    in_fence: str | None = None
    while position < len(text):
        if position in line_ends:
            end = line_ends[position]
            line = text[position:end]
            if fence := _FENCE_RE.match(line):
                if in_fence is None:
                    in_fence = fence.group(1)
                elif _closes_fence(line, in_fence):
                    in_fence = None
                position = end
                continue
            if in_fence is not None:
                position = end
                continue
        if not text.startswith("{{", position):
            position += 1
            continue
        # Historical keys own their contents, so a literal opener inside an
        # earlier key cannot establish a Markdown scope for later references.
        literal_end = next(
            (
                end
                for start, end in literal_spans
                if start <= position < end
                and not any(left <= start < right for left, right in accepted_ranges)
            ),
            None,
        )
        before = position
        while before and text[before - 1] == "\\":
            before -= 1
        # The former renderer expanded references inside inline/HTML literals,
        # including their backslashes; only escaped prose openers stay literal.
        if (position - before) % 2 and literal_end is None:
            position += 1
            continue
        marker = read_question_marker(text, position)
        if literal_end is not None and (marker is None or marker.end > literal_end):
            position = literal_end
            continue
        if marker is None:
            break
        token = f"{marker_prefix}{len(markers)}\x00"
        markers[token] = (
            text[marker.start : marker.end],
            marker.name,
            bool(marker.start and text[marker.start - 1] == "%"),
        )
        masked.extend((text[at : marker.start], token))
        accepted_ranges.append((marker.start, marker.end))
        at = position = marker.end
    masked.append(text[at:])
    return "".join(masked), markers, re.compile(re.escape(marker_prefix) + r"\d+\x00")


def historical_collected_questions(script: str) -> frozenset[str]:
    """Read pre-migration main-script declarations only to match old 2.0 prompts."""
    _projected, markers, _tokens = _project_legacy_markers(script)
    return frozenset(
        name
        for _raw, name, assignment in markers.values()
        if assignment and name is not None
    )


def historical_reference_names(bundle: ScriptBundle) -> frozenset[str]:
    """Find former host reads even when no value was ever saved for them."""
    collected = historical_collected_questions(bundle.script)
    return frozenset(
        name
        for source in (bundle.script, bundle.constraints or "")
        for _projected, markers, _tokens in (_project_legacy_markers(source),)
        for _raw, name, assignment in markers.values()
        if name is not None and not assignment and name not in collected
    )


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
    """Match known sections using the historical main script's collection scope."""
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
