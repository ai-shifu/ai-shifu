"""Finite continuation witnesses for the native inline HTML grammar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from markdownflow.syntax.parser.document_blocks import HTML_BLOCK_TAGS

if TYPE_CHECKING:
    from collections.abc import Iterable

_RAW_TAGS = ("script", "style", "pre", "textarea")
_TAG_PREFIXES = frozenset(
    tag[:width]
    for tag in (*_RAW_TAGS, *HTML_BLOCK_TAGS)
    for width in range(1, len(tag) + 1)
)
_State = tuple[str, str]
_States = frozenset[_State]


def _letter(character: str) -> bool:
    return "a" <= character <= "z" or "A" <= character <= "Z"


def _name(name: str, character: str) -> str:
    candidate = name + character.lower()
    return candidate if candidate in _TAG_PREFIXES else "x"


def _attribute_start(character: str) -> bool:
    return _letter(character) or character in "_:"


def _unquoted(character: str) -> bool:
    return character not in " \t\r\n\"'=<>`"


# Tag whitespace is spaces and tabs with at most one line ending. A whitespace
# kind carries its line-ending budget as a suffix: "" (none seen), "/cr" (a
# carriage return that a line feed may still complete) or "/nl" (spent).
_OVER_BUDGET = "!"


def _space(eol: str, character: str) -> str | None:
    """Return the next line-ending budget, None for non-space, or over budget."""
    if character in " \t":
        return "nl" if eol else ""
    if character == "\n":
        return _OVER_BUDGET if eol == "nl" else "nl"
    if character == "\r":
        return "cr" if not eol else _OVER_BUDGET
    return None


def _step(state: _State, character: str) -> tuple[Iterable[_State], bool]:
    kind, name = state
    kind, _, eol = kind.partition("/")

    def one(next_kind: str, next_name: str = name) -> tuple[Iterable[_State], bool]:
        return ((next_kind, next_name),), False

    def space(next_kind: str) -> tuple[Iterable[_State], bool] | None:
        """Continue a whitespace run in ``next_kind``, or None for non-space."""
        budget = _space(eol if next_kind == kind else "", character)
        if budget is None:
            return None
        if budget == _OVER_BUDGET:
            return (), False
        return one(next_kind + ("/" + budget if budget else ""))

    if kind == "lt":
        if _letter(character):
            return one("name", _name("", character))
        return (
            one({"/": "close_start", "!": "bang", "?": "pi"}[character])
            if character in "/!?"
            else ((), False)
        )
    if kind == "close_start":
        return (
            one("close_name", _name("", character))
            if _letter(character)
            else ((), False)
        )
    if kind in ("name", "close_name"):
        if _letter(character) or "0" <= character <= "9" or character == "-":
            return one(kind, _name(name, character))
        if (spaced := space("space" if kind == "name" else "close_space")) is not None:
            return spaced
        if character == ">":
            return (), True
        return (
            one("slash_direct") if kind == "name" and character == "/" else ((), False)
        )
    if kind == "close_space":
        if (spaced := space(kind)) is not None:
            return spaced
        return (), character == ">"
    if kind in ("space", "attr_space", "quoted_end"):
        if (
            spaced := space("attr_space" if kind == "attr_space" else "space")
        ) is not None:
            return spaced
        if character == ">":
            return (), True
        if character == "/":
            return one("slash")
        if kind == "attr_space" and character == "=":
            return one("before_value")
        if kind != "quoted_end" and _attribute_start(character):
            return one("attr")
        return (), False
    if kind == "attr":
        if _attribute_start(character) or "0" <= character <= "9" or character in ".-":
            return one(kind)
        if (spaced := space("attr_space")) is not None:
            return spaced
        if character == "=":
            return one("before_value")
        if character == ">":
            return (), True
        return one("slash") if character == "/" else ((), False)
    if kind == "before_value":
        if (spaced := space(kind)) is not None:
            return spaced
        if character in "\"'":
            return one("double" if character == '"' else "single")
        return one("unquoted") if _unquoted(character) else ((), False)
    if kind in ("single", "double"):
        quote = "'" if kind == "single" else '"'
        return one("quoted_end" if character == quote else kind)
    if kind == "unquoted":
        if character == ">":
            return (), True
        if _unquoted(character):
            return one(kind)
        spaced = space("space")
        return spaced if spaced is not None else ((), False)
    if kind in ("slash", "slash_direct"):
        return (), character == ">"
    if kind == "bang":
        if _letter(character):
            return one("declaration")
        return (
            one("comment_dash")
            if character == "-"
            else one("cdata_prefix", "<![")
            if character == "["
            else ((), False)
        )
    if kind == "comment_dash":
        return one("comment_start") if character == "-" else ((), False)
    if kind == "cdata_prefix":
        prefix = name + character
        if not "<![CDATA[".startswith(prefix):
            return (), False
        return one("cdata0", "") if prefix == "<![CDATA[" else one(kind, prefix)
    if kind == "declaration":
        return one(kind) if character != ">" else ((), True)
    if kind.startswith("comment"):
        if kind in ("comment_start", "comment_start_dash") and character == ">":
            return (), True
        if kind == "comment2":
            return ((), True) if character == ">" else one("comment0")
        if character == "-":
            return one(
                "comment_start_dash"
                if kind == "comment_start"
                else "comment2"
                if kind in ("comment1", "comment_start_dash")
                else "comment1"
            )
        return one("comment0")
    if kind in ("pi", "pi_question"):
        if kind == "pi_question" and character == ">":
            return (), True
        return one("pi_question" if character == "?" else "pi")
    if kind.startswith("cdata"):
        if kind == "cdata2" and character == ">":
            return (), True
        return one(
            "cdata2"
            if character == "]" and kind != "cdata0"
            else "cdata1"
            if character == "]"
            else "cdata0"
        )
    return (), False


def _witness(states: _States, tokens: str) -> str:
    # The grammar is deterministic: a character is tag space or value text,
    # never both, so a viable prefix always has exactly one lexer state.
    kind, name = min(states)
    kind, _, eol = kind.partition("/")
    # Replay a spent or pending line ending so the witness keeps its budget.
    ending = {"": "", "cr": "\r", "nl": "\n"}[eol]
    kept = tokens + "x"
    if kind == "lt":
        return "<"
    if kind == "close_start":
        return "</"
    if kind == "bang":
        return "<!"
    if kind == "comment_dash":
        return "<!-"
    if kind == "cdata_prefix":
        return name
    if kind == "declaration":
        return "<!A" + kept
    if kind in ("pi", "pi_question"):
        return "<?" + kept + ("?" if kind == "pi_question" else "")
    if kind.startswith("cdata"):
        return "<![CDATA[" + kept + "]" * int(kind[-1])
    if kind == "comment_start":
        return "<!--"
    if kind == "comment_start_dash":
        return "<!---"
    if kind.startswith("comment"):
        return "<!--" + kept + "-" * int(kind[-1])
    if kind in ("close_name", "close_space"):
        return "</" + name + (" " + ending if kind == "close_space" else "")
    tag = "<" + name
    if kind == "name":
        return tag
    if kind == "slash_direct":
        return tag + "/"
    if kind in ("single", "double"):
        return tag + " x=" + ("'" if kind == "single" else '"') + kept
    if kind == "quoted_end":
        return tag + ' x="' + kept + '"'
    tag += ' data-x="' + kept + '"'
    return (
        tag
        + {
            "space": " ",
            "attr_space": " y ",
            "attr": " y",
            "before_value": " y=",
            "unquoted": " y=x",
            "slash": "/",
        }[kind]
        + ending
    )


def pending_html_prefix(
    text: str, start: int, *, tokens: str = ""
) -> tuple[int, str] | None:
    """Return a viable unfinished native HTML token using a bounded witness.

    Continuations are memoized by source offset and finite lexer state, so an
    invalid outer tag cannot repeatedly rescan long nested candidate suffixes.
    """
    memo: dict[tuple[int, _States], tuple[str, int, _States]] = {}
    opening = text.find("<", start)
    while opening >= 0:
        states: _States = frozenset({("lt", "")})
        at = opening + 1
        path: list[tuple[int, _States]] = []
        while at < len(text):
            key = at, states
            if key in memo:
                outcome, end, states = memo[key]
                break
            path.append(key)
            following: set[_State] = set()
            complete = False
            for state in states:
                choices, matched = _step(state, text[at])
                following.update(choices)
                complete |= matched
            at += 1
            states = frozenset(following)
            if complete or not states:
                outcome, end = ("complete" if complete else "invalid"), at
                break
        else:
            outcome, end = "pending", len(text)
        for key in path:
            memo[key] = outcome, end, states
        if outcome == "pending":
            return opening, _witness(states, tokens)
        opening = text.find("<", end if outcome == "complete" else opening + 1)
    return None
