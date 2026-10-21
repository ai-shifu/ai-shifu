"""Clean classified Markdown prose; the caller owns element classification."""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline.autolink import autolink
from markdown_it.rules_inline.backticks import backtick
from markdown_it.rules_inline.html_inline import html_inline
from markdown_it.rules_inline.image import image
from markdown_it.rules_inline.link import link
from markdown_it.rules_inline.state_inline import StateInline

_MARKERS = re.compile(r"!?={3,}")
_MARKER_LINE = re.compile(r"[ \t]*!={3,}[ \t]*")
_MARKER_PREFIX = re.compile(r"^([ \t]*)(!?={3,})")
_Rule = Callable[[StateInline, bool], bool]


def clean_markdown_text(source: str, environment: dict[str, Any] | None = None) -> str:
    """Remove prose markers using native code/link rules and reference definitions.

    Only formatter-classified prose belongs here. HTML, SVG and code elements
    bypass this function. A supplied environment can share native reference
    definitions across pieces; forward definitions require the caller to wait.
    """
    if environment is None and not _MARKERS.search(source):
        return source
    if not any(char in source for char in "`[<"):
        return "".join(
            ""
            if _MARKER_LINE.fullmatch(line.removesuffix("\n").removesuffix("\r"))
            else _MARKERS.sub("", line)
            for line in re.split(r"(?<=\n)|(?<=\r)(?!\n)", source)
        )

    def record(rule: _Rule, kind: str) -> _Rule:
        def wrapped(state: StateInline, silent: bool) -> bool:
            start, count = state.pos, len(state.tokens)
            label_start = start + (2 if kind == "image" else 1)
            label_end = (
                state.md.helpers.parseLinkLabel(state, label_start - 1, kind == "link")
                if not silent and kind in ("link", "image")
                else -1
            )
            accepted = rule(state, silent)
            if not accepted or silent:
                return accepted
            protected: list[tuple[int, int]] = []
            if kind == "backticks":
                if len(state.tokens) > count and state.tokens[-1].type == "code_inline":
                    protected.append((start, state.pos))
            elif kind in ("autolink", "html_inline"):
                protected.append((start, state.pos))
            elif label_end >= 0:
                suffix = state.src[label_end + 1 : state.pos]
                if suffix in ("", "[]"):
                    # A shortcut/collapsed reference's visible label is its key.
                    protected.append((start, state.pos))
                else:
                    protected.append((label_end + 1, state.pos))
                if kind == "image":
                    state.tokens[-1].meta["alt_offset"] = label_start
            if protected:
                token = next(
                    token
                    for token in state.tokens[count:]
                    if token.type
                    in ("code_inline", "link_open", "image", "html_inline")
                )
                token.meta["marker_opaque"] = protected
            return accepted

        return wrapped

    parser = MarkdownIt("commonmark", {"inline_definitions": True})
    parser.disable(["html_block", "fence", "code"])
    for name, rule in (
        ("backticks", backtick),
        ("link", link),
        ("image", image),
        ("autolink", autolink),
        ("html_inline", html_inline),
    ):
        parser.inline.ruler.at(name, record(rule, name))
    shared_environment = environment if environment is not None else {}
    lines = re.split(r"(?<=\n)|(?<=\r)(?!\n)", source)
    prefixes = [_MARKER_PREFIX.match(line) for line in lines]
    tokens = parser.parse(
        source, deepcopy(shared_environment) if any(prefixes) else shared_environment
    )
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    protected = bytearray(len(source))

    def ranges(children: list[Any], offset: int = 0) -> list[tuple[int, int]]:
        result = []
        for child in children:
            result.extend(
                (offset + first, offset + last)
                for first, last in child.meta.get("marker_opaque", ())
            )
            if child.type == "image":
                result.extend(
                    ranges(child.children or [], offset + child.meta["alt_offset"])
                )
        return result

    def protect(tokens: list[Any]) -> None:
        for token in tokens:
            if token.map is None:
                continue
            first_line, last_line = token.map
            if token.type == "definition":
                first, last = offsets[first_line], offsets[last_line]
                protected[first:last] = b"\1" * (last - first)
            if token.type != "inline":
                continue
            # Native inline source removes container prefixes and virtual indentation.
            # Map its remaining literal characters back to the original physical line.
            positions: dict[int, int] = {}
            inline_offset = 0
            for number, content in enumerate(token.content.split("\n"), first_line):
                if number >= last_line:
                    break
                body = content.lstrip(" \t")
                physical = lines[number].replace("\0", "\ufffd")
                column = physical.rfind(body) if body else -1
                if column >= 0:
                    skipped = len(content) - len(body)
                    positions.update(
                        (
                            inline_offset + skipped + index,
                            offsets[number] + column + index,
                        )
                        for index in range(len(body))
                    )
                inline_offset += len(content) + 1
            for first, last in ranges(token.children or []):
                for index in range(first, last):
                    if index in positions:
                        protected[positions[index]] = 1

    protect(tokens)
    if any(prefixes):
        # Remove only prefixes outside native opaque spans. Otherwise a line in
        # multiline code could become a blank line/heading and invent a reference.
        candidates = [
            prefix
            if prefix
            and not any(protected[offsets[number] : offsets[number] + prefix.end()])
            else None
            for number, prefix in enumerate(prefixes)
        ]
        candidate = "".join(
            prefix.group(1) + line[prefix.end() :] if prefix else line
            for line, prefix in zip(lines, candidates, strict=True)
        )
        definitions = (
            parser.parse(candidate, shared_environment) if candidate != source else []
        )
        protect(parser.parse(source, shared_environment))
        for token in definitions:
            if token.type == "definition" and token.map is not None:
                first_line, last_line = token.map
                prefix = candidates[first_line]
                first = offsets[first_line] + (prefix.end() if prefix else 0)
                last = offsets[last_line]
                protected[first:last] = b"\1" * (last - first)
    removed = bytearray(len(source))
    for match in _MARKERS.finditer(source):
        first, last = match.span()
        if not any(protected[first:last]):
            removed[first:last] = b"\1" * (last - first)
    for number, line in enumerate(lines):
        first, last = offsets[number], offsets[number + 1]
        if _MARKER_LINE.fullmatch(
            line.removesuffix("\n").removesuffix("\r")
        ) and not any(protected[first:last]):
            removed[first:last] = b"\1" * (last - first)
    return "".join(char for index, char in enumerate(source) if not removed[index])
