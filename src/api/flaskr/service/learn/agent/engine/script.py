"""Script bundle, 1.0-notation detection and variable substitution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# Anything that only makes sense with the MarkdownFlow 1.0 syntax note.
V1_SYNTAX_RE = re.compile(
    r"(^---[ \t]*$)"  # block separator
    r"|(?<!\\)\?\[[^\]\n]*\](?!\()"  # ?[...] interaction (not an escaped one, not a link)
    r"|%?\{\{[^{}\n]+\}\}"  # {{var}} / %{{var}}
    r"|^!?===.*$",  # ===preserved=== / !=== fences
    re.MULTILINE,
)
_FENCE_RE = re.compile(r"(?m)^(`{3,}|~{3,}).*$")


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


_VAR_RE = re.compile(r"(?<!%)\{\{\s*([^{}\s]+)\s*\}\}")
# `%{{name}}` marks a variable this script collects during the lesson, in a question or an
# instruction to remember something.
_COLLECTED_RE = re.compile(r"%\{\{\s*([^{}\s]+)\s*\}\}")


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
    return bool(V1_SYNTAX_RE.search(_strip_fences(text)))


def _strip_fences(text: str) -> str:
    out: list[str] = []
    in_fence: str | None = None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if m:
            if in_fence is None:
                in_fence = m.group(1)
            elif _closes_fence(line, in_fence):
                in_fence = None
            continue
        if in_fence is None:
            out.append(line)
    return "\n".join(out)


def collected_names(text: str) -> frozenset[str]:
    """Return the variables this script fills in during the lesson, named by `%{{name}}`."""
    return frozenset(_COLLECTED_RE.findall(text))


def substitute_variables(
    text: str, values: Mapping[str, Any], *, collected: frozenset[str] = frozenset()
) -> str:
    """Replace `{{name}}` with `values[name]` outside fenced code blocks.

    `%{{name}}` and unknown names are left untouched so the model can still see what the author
    meant.

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

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name in collected:
            return m.group(0)
        if name not in values or values[name] in (None, ""):
            return m.group(0)
        v = values[name]
        return ", ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)

    out: list[str] = []
    in_fence: str | None = None
    for line in text.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        if m:
            if in_fence is None:
                in_fence = m.group(1)
            elif _closes_fence(line, in_fence):
                in_fence = None
            out.append(line)
            continue
        out.append(line if in_fence else _VAR_RE.sub(repl, line))
    return "".join(out)


def render_first_prompt(bundle: ScriptBundle, memory: Mapping[str, Any]) -> str:
    """Compose the first user message.

    Learner memory first, then the script with its variables substituted, then optional
    constraints and extras.
    """
    collected = collected_names(bundle.script)
    # What this lesson is about to ask for is not something the learner has already said. Shown
    # in memory, an earlier answer is read as the current one -- and a model that has both a
    # stale fact and a fresh tool result tends to trust the fact.
    remembered = {k: v for k, v in memory.items() if k not in collected}
    mem = json.dumps(remembered, ensure_ascii=False, indent=2) if remembered else "{}"
    parts = [
        f"<memory>\n{mem}\n</memory>",
        f"<script>\n{substitute_variables(bundle.script, memory, collected=collected)}\n</script>",
    ]
    if bundle.constraints:
        parts.append(
            f"<constraints>\n"
            f"{substitute_variables(bundle.constraints, memory, collected=collected)}\n"
            f"</constraints>"
        )
    for name, body in bundle.extras.items():
        parts.append(f'<extra name="{name}">\n{body}\n</extra>')
    return "\n\n".join(parts)
