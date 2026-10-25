"""Script bundle, notation detection and literal prompt assembly."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .marker_context import analyze_marker_context, marker_syntax_source
from .questions import QUESTION_SOURCE, find_interaction_spans, normalize_question

# Anything that only makes sense with the MarkdownFlow 1.0 syntax note.
V1_SYNTAX_RE = re.compile(
    r"(^---[ \t]*$)"  # block separator
    r"|(?<!\\)\?\[[^\]\n]*\](?!\()"  # ?[...] interaction (not an escaped one, not a link)
    r"|^!?===.*$",  # ===preserved=== / !=== fences
    re.MULTILINE,
)
_FENCE_RE = re.compile(r"(?m)^(`{3,}|~{3,}).*$")


def _closes_fence(line: str, opening: str) -> bool:
    """Report whether this line closes a fence opened with `opening`.

    A fence closes on a line of the same marker, at least as long as the opener, and nothing else.
    Keeping the opening length matters: a ``` line inside a ```` block is content, and closing on
    it would expose the rest of the block to question scanning and notation detection.
    """
    # rstrip, not strip: the opening fences recognized here must start at column 0, so an indented
    # marker is content -- a lesson showing a fenced block inside one would otherwise close early.
    stripped = line.rstrip()
    return len(stripped) >= len(opening) and stripped == opening[0] * len(stripped)


_PRESERVED_LINE_RE = re.compile(r"^[ \t]*===(.+?)===[ \t]*$")
_QUESTION = re.compile(r"^\s*" + QUESTION_SOURCE)


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


def detect_v1_syntax(text: str) -> bool:
    """Report whether the text uses any MarkdownFlow 1.0 notation outside fenced code blocks."""
    source = _strip_fences(text)
    context = analyze_marker_context(source, fence_indent=3)
    return bool(V1_SYNTAX_RE.search(source)) or any(
        find_interaction_spans(
            source, syntax_source=marker_syntax_source(source, context)
        )
    )


def _project_question_markers(
    text: str,
) -> tuple[str, dict[str, str], re.Pattern[str]]:
    """Protect actual question text while inspecting the surrounding Markdown."""
    marker_prefix = "\x00mdf-question:"
    while marker_prefix in text:
        marker_prefix += ":"
    markers = {}
    masked: list[str] = []
    at = 0
    for marker in analyze_marker_context(text, fence_indent=0).markers:
        token = f"{marker_prefix}{len(markers)}\x00"
        markers[token] = text[marker.start : marker.end]
        masked.extend((text[at : marker.start], token))
        at = marker.end
    masked.append(text[at:])
    return "".join(masked), markers, re.compile(re.escape(marker_prefix) + r"\d+\x00")


def _strip_fences(text: str) -> str:
    projected, markers, tokens = _project_question_markers(text)
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
    return tokens.sub(lambda match: markers[match.group(0)], "\n".join(out))


def collected_questions(text: str) -> frozenset[str]:
    """Return memory questions declared at the start of actual authored controls.

    Standalone brace text, examples, links and code do not declare questions.
    The document scanner keeps punctuation inside question text opaque.
    """
    context = analyze_marker_context(text, fence_indent=3)
    return frozenset(
        question
        for start, end in find_interaction_spans(
            text, syntax_source=marker_syntax_source(text, context)
        )
        if (match := _QUESTION.match(text[start + 2 : end - 1]))
        if (question := normalize_question(match.group(1))) is not None
    )


def final_preserved_line(text: str) -> str | None:
    """Return a unique inline verbatim line at the script's physical end, if present.

    Fenced examples and repeated author blocks are not a single terminal line. This is a
    narrow display anchor, never evidence that every preceding instruction was completed.
    """
    projected, markers, tokens = _project_question_markers(text)

    def restore(match: re.Match[str]) -> str:
        return markers[match.group(0)]

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


def render_memory_section(
    bundle: ScriptBundle,
    memory: Mapping[str, Any],
    *,
    limit: int | None = None,
    priority: frozenset[str] = frozenset(),
) -> tuple[str, bool]:
    """Project whole values into one bounded JSON payload without editing stored memory.

    Host-priority keys come first; other keys retain input order. A value that
    does not fit is omitted, never shortened. Authored text remains literal.
    """
    collected = collected_questions(bundle.script)
    remembered = {k: v for k, v in memory.items() if k not in collected}
    selected = remembered
    if limit is not None:
        if limit < 2:
            message = "memory context limit must fit an empty JSON object"
            raise ValueError(message)
        preferred = priority
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

    Learner memory first, then the author's literal script, constraints and extras.
    """
    # What this lesson is about to ask for is not something the learner has already said. Shown
    # in memory, an earlier answer is read as the current one -- and a model that has both a
    # stale fact and a fresh tool result tends to trust the fact.
    parts = [
        render_memory_section(
            bundle, memory, limit=memory_limit, priority=memory_priority
        )[0],
        f"<script>\n{bundle.script}\n</script>",
    ]
    if bundle.constraints:
        parts.append(f"<constraints>\n{bundle.constraints}\n</constraints>")
    for name, body in bundle.extras.items():
        parts.append(f'<extra name="{name}">\n{body}\n</extra>')
    return "\n\n".join(parts)
