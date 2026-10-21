"""Strip MarkdownFlow's verbatim markers from what the engine says.

A script marks content the model must reproduce word for word with `===like this===`, or between
`!===` fence lines. A 1.0 lesson never shows those markers: the parser recognises the block, emits
its content as it is, and the model never sees it. The 2.0 engine hands the model the whole script
and asks it to reproduce such content exactly -- which it does, markers included. Left in, they are
rendered, spoken and subtitled: a listener heard "===帮助 100 万人顺利走进 AGI 时代===".

The markers are the script's syntax, not the lesson's content, so they are removed here from the
engine's text before it reaches anything that shows or speaks it, in every mode. What sits between
them is kept, untouched.

Text arrives in chunks that can split a marker, so a trailing run of `=` that could still become
one is held back until the next chunk, or released as it is when the turn ends. A line that could
still turn out to be a fence -- a code fence, or a `!===` line -- is held whole until its end, since
that is a decision about the line, not about a fragment of it. Code is passed through as it is:
`a === b` inside a fence or an HTML script is an operator, not a marker.

Rare reference labels and ambiguous Markdown block starts need the whole turn's block context.
Their unprocessed suffix waits until `flush`; ordinary text continues to stream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from itertools import chain
from string import punctuation
from typing import TYPE_CHECKING

from markdown_flow.formatter.patterns import block_html_open_re, heading_re
from markdown_it import MarkdownIt
from markdown_it.common.html_re import HTML_OPEN_CLOSE_TAG_RE
from markdown_it.common.utils import normalizeReference
from markdown_it.rules_inline.html_inline import html_inline as parse_inline_html
from markdown_it.rules_inline.image import image as parse_image

if TYPE_CHECKING:
    from collections.abc import Callable

    from markdown_it.rules_inline.state_inline import StateInline
    from markdown_it.token import Token

# The same shapes `markdown_flow` recognises: a fence line of `!` and three or more `=`, and the
# inline tokens `!===` and `===`.
_FENCE_LINE = re.compile(r"^[ \t]*!={3,}[ \t]*$")
# A code fence opens with three or more backticks or tildes; it closes only with a line of the
# same character, at least as long, and nothing after it (CommonMark). A tilde line does not
# close a backtick fence, a shorter fence does not close a longer one, and a line with trailing
# text is content inside the block.
_CODE_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
_CODE_FENCE_CLOSE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*$")
_CODE_INDENT = re.compile(r"^(?: {4}| {0,3}\t)")
_CONTAINER_HEAD = re.compile(r"^[ ]{0,3}(?:>|(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t]|$))")
_CONTAINER_PREFIX = re.compile(
    r"^[ ]{0,3}(?:>|[-+*](?=[ \t]|$)|[0-9]{1,9}(?:[.)](?=[ \t]|$)|$))"
)
_MARKDOWN_BLOCK_CANDIDATE = re.compile(
    r"^[ \t]*(?:#{1,6}(?=[ \t]|$)|>|(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t]|$)"
    r"|(?:[-*_][ \t]*){3,}$|[=-]+[ \t]*$)"
)
_MARKERS = re.compile(r"!?={3,}")
# An unfinished line that may still become a fence line of either kind.
_MAY_BE_FENCE = re.compile(r"^[ ]{0,3}[`~]|^[ \t]*!?=*[ \t]*$")
# The tail of an unfinished line that may still become a marker once more text arrives.
_PARTIAL_TAIL = re.compile(r"!?=*$")
_HTML_TAG_HEAD = re.compile(r"</?([a-zA-Z][a-zA-Z0-9:-]*)(?=[\s/>])")
_HTML_TAG_PREFIX = re.compile(r"</?[a-zA-Z][a-zA-Z0-9:-]*$")
_HTML_DOCTYPE_HEAD = re.compile(r"<!DOCTYPE(?=[\s>])", re.IGNORECASE)
_HTML_ROOT_HEAD = re.compile(r"<(?:html|body|svg)(?=[\s>/])", re.IGNORECASE)
_HTML_RAW_BLOCK_HEAD = re.compile(
    r"<(?:script|style|textarea)(?=[\s>]|$)", re.IGNORECASE
)
_HTML_OPAQUE = {"<!--": "-->", "<![CDATA[": "]]>", "<?": "?>"}
# Raw-text and RCDATA bodies cannot open nested HTML elements. Only script/style
# contain code; other text-only elements still have prose markers removed.
_RAW_TEXT_END = {
    tag: re.compile(rf"</{tag}(?=[\s/>])", re.IGNORECASE)
    for tag in (
        "script",
        "style",
        "textarea",
        "title",
        "iframe",
        "xmp",
        "noembed",
        "noframes",
    )
}
_PROSE_SPECIAL = re.compile(r"[<`\\\[\]]")
_BACKTICKS = re.compile(r"`+")


def _raw_block_head(text: str) -> bool:
    """Recognize the leading raw-text blocks already supported by the formatter."""
    candidate = text.lstrip(" \t")
    head = _HTML_TAG_HEAD.match(candidate)
    return _CODE_INDENT.match(text) is None and (
        _HTML_RAW_BLOCK_HEAD.match(candidate) is not None
        or (
            head is not None
            and head.group(1).lower() in _RAW_TEXT_END
            and block_html_open_re.match(candidate) is not None
        )
    )


def _run_end(text: str, start: int) -> int:
    """Find the end of a repeated Markdown delimiter or escape character."""
    end = start + 1
    while end < len(text) and text[end] == text[start]:
        end += 1
    return end


def _container_code_candidate(line: str) -> bool:
    """Find potential container code; the block parser makes the actual decision."""
    found = False
    tab = False
    while match := _CONTAINER_HEAD.match(line):
        found = True
        line = line[match.end() :]
        if line.startswith((" ", "\t")):
            # Consume one separator only, keeping any extra code indentation.
            # Tabs can leave virtual columns, so conservatively ask the parser.
            tab |= line.startswith("\t")
            line = line[1:]
    return found and bool(
        tab or _CODE_INDENT.match(line) or _CODE_FENCE_OPEN.match(line)
    )


def _container_raw_block_candidate(line: str) -> bool:
    """Defer possible raw HTML in a container to the complete block parser."""
    found = False
    while match := _CONTAINER_HEAD.match(line):
        found = True
        line = line[match.end() :]
        if line.startswith((" ", "\t")):
            line = line[1:]
    return found and _HTML_RAW_BLOCK_HEAD.match(line.lstrip(" \t")) is not None


def _has_block_candidate(text: str, scanned: int) -> bool:
    """Find possible block starts; only the full parser decides inline boundaries."""
    newline = text.rfind("\n", 0, scanned)
    if newline < 0:
        newline = text.find("\n")
    while newline >= 0:
        start = newline + 1
        newline = text.find("\n", start)
        line = text[start : newline if newline >= 0 else None]
        if (
            _MARKDOWN_BLOCK_CANDIDATE.match(line)
            or _container_code_candidate(line)
            or _container_raw_block_candidate(line)
        ):
            return True
    return False


def _inline_boundary(
    text: str,
    start: int,
    scanned: int = 0,
    code_boundaries: frozenset[str] = frozenset(),
    raw_block_openers: frozenset[str] = frozenset(),
    inline_boundaries: frozenset[str] = frozenset(),
) -> int:
    """Locate a paragraph or block boundary that ends an inline candidate."""
    # Inline syntax cannot cross a paragraph break or consume a code/HTML block. Revisit the previous
    # chunk's last line too: its opening tag may only now have become complete.
    newline = text.rfind("\n", start, start + scanned)
    if newline < 0:
        newline = text.find("\n", start)
    while newline >= 0:
        line_start = newline + 1
        newline = text.find("\n", line_start)
        raw_line = text[line_start : newline if newline >= 0 else None]
        line = _MARKERS.sub("", raw_line)
        candidate = line.lstrip(" \t")
        if (
            (newline >= 0 and not raw_line.strip(" \t"))
            or raw_line[:1] in code_boundaries
            or raw_line[:1] in inline_boundaries
            or any(opener in raw_line for opener in raw_block_openers)
            or _CODE_FENCE_OPEN.match(raw_line)
            or _FENCE_LINE.match(raw_line)
            or block_html_open_re.match(line)
            or _HTML_ROOT_HEAD.match(candidate)
            or _HTML_DOCTYPE_HEAD.match(candidate)
            or any(candidate.startswith(opener) for opener in _HTML_OPAQUE)
        ):
            return line_start
    return len(text)


def _code_span_end(
    text: str,
    start: int,
    scanned: int | None,
    *,
    final: bool,
    code_boundaries: frozenset[str] = frozenset(),
    raw_block_openers: frozenset[str] = frozenset(),
    inline_boundaries: frozenset[str] = frozenset(),
) -> tuple[int | None, int | None]:
    """Pair backticks; a None scan offset means a block forced an unmatched opener."""
    if scanned is None:
        return None, None
    opening_end = _run_end(text, start)
    width = opening_end - start
    boundary = _inline_boundary(
        text, start, scanned, code_boundaries, raw_block_openers, inline_boundaries
    )
    for closing in _BACKTICKS.finditer(
        text, max(opening_end, start + scanned), boundary
    ):
        # The next chunk may extend this run; do not close it prematurely.
        if closing.end() == len(text) and not final:
            return None, closing.start() - start
        if closing.end() - closing.start() == width:
            return closing.end(), 0
    if boundary < len(text):
        # The caller replays unmatched source through the line/fence parser too.
        return None, None
    return None, len(text) - start


@dataclass
class _LinkSuffix:
    """Incremental progress through a link destination and optional title."""

    position: int = 1
    stage: str = "open"
    depth: int = 0
    closer: str = ""
    separated: bool = False
    reference: bool = False
    reference_end: int = 0


@dataclass
class _LinkLabel:
    """Images may contain links; a link cannot contain another active link."""

    image: bool
    active: bool = True
    contains_link: bool = False
    reference: bool = False
    content: bool = False
    source: str | None = ""
    full_reference: bool = False
    reference_image: bool = False
    restore_outer: tuple[tuple[_LinkLabel, bool, bool], ...] = ()


def _reference_label_end(text: str, start: int = 0) -> int | None:
    """Find a reference label's unescaped end, rejecting nested or overlong labels."""
    pos = start
    while pos < len(text) and pos - start <= 999:
        char = text[pos]
        if char == "\\":
            pos += 2
        elif char == "[":
            return None
        elif char == "]":
            return pos
        else:
            pos += 1
    return None


def _reference_name(label: str) -> str:
    """Match reference names after the same marker removal used in output labels."""
    return normalizeReference(_MARKERS.sub("", label))


def _image_with_alt_range(state: StateInline, silent: bool) -> bool:
    """Keep the native image rule's confirmed alt bounds in its own inline source."""
    start = state.pos
    matched = parse_image(state, silent)
    if matched and not silent:
        token = state.tokens[-1]
        token.meta["marker_alt_range"] = (start + 2, start + 2 + len(token.content))
    return matched


def _html_with_source_range(state: StateInline, silent: bool) -> bool:
    """Keep native HTML token bounds so image attributes stay opaque to Markdown."""
    start = state.pos
    matched = parse_inline_html(state, silent)
    if matched and not silent:
        state.tokens[-1].meta["marker_html_range"] = (start, state.pos)
    return matched


def _image_html_positions(
    token: Token, source_lines: list[str], offsets: list[int]
) -> dict[int, str]:
    """Map confirmed image metadata through each physical line's container prefix."""
    ranges: list[tuple[int, int]] = []
    opaque_ranges: list[tuple[int, int]] = []

    def collect_html(children: list[Token], base: int) -> None:
        for child in children:
            if child.type == "html_inline":
                start, end = child.meta["marker_html_range"]
                opaque_ranges.append((base + start, base + end))
            elif child.type == "image":
                start, _ = child.meta["marker_alt_range"]
                collect_html(child.children or [], base + start)

    for child in token.children or ():
        if child.type == "image":
            start, end = child.meta["marker_alt_range"]
            ranges.append((start, end))
            collect_html(child.children or [], start)
    if not ranges or token.map is None:
        return {}
    opaque_ranges.sort()
    positions: dict[int, str] = {}
    range_index = opaque_index = content_offset = 0
    for index, line in enumerate(token.content.splitlines(keepends=True), token.map[0]):
        # Block parsing strips quote/list prefixes and can leave virtual tab indentation.
        leading = len(line) - len(line.lstrip(" \t"))
        body = line[leading:].rstrip("\r\n")
        raw_line = source_lines[index].replace("\x00", "\ufffd")
        column = raw_line.rfind(body)
        if column >= 0:
            for match in re.finditer(r"[<`~\\\[\]!=]", line):
                position = content_offset + match.start()
                while range_index < len(ranges) and ranges[range_index][1] <= position:
                    range_index += 1
                if range_index == len(ranges):
                    return positions
                while (
                    opaque_index < len(opaque_ranges)
                    and opaque_ranges[opaque_index][1] <= position
                ):
                    opaque_index += 1
                opaque = (
                    opaque_index < len(opaque_ranges)
                    and opaque_ranges[opaque_index][0] <= position
                )
                if ranges[range_index][0] <= position and (match[0] == "<" or opaque):
                    source_position = offsets[index] + column + match.start() - leading
                    positions[source_position] = match[0]
        content_offset += len(line)
    return positions


def _reference_replay_source(
    source: str, mask_start: int
) -> tuple[
    str,
    frozenset[str],
    dict[int, str],
    frozenset[str],
    frozenset[str],
    frozenset[str],
    dict[int, str],
]:
    """Protect parser-confirmed source and boundaries only after the suffix that stopped streaming."""
    parser = MarkdownIt("commonmark", {"inline_definitions": True})
    parser.inline.ruler.at("image", _image_with_alt_range)
    parser.inline.ruler.at("html_inline", _html_with_source_range)
    tokens = parser.parse(source)
    source_lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in source_lines:
        offsets.append(offsets[-1] + len(line))
    present = set(source)
    candidates = chain(
        range(0xE000, 0xF900),
        range(0xF0000, 0xFFFFE),
        range(0x100000, 0x10FFFE),
        range(0x100, 0xD800),
    )
    masks = {
        char: chr(next(code for code in candidates if chr(code) not in present))
        for char in "<`~\\[]!="
    }
    image_masks = {
        char: chr(next(code for code in candidates if chr(code) not in present))
        for char in masks
    }
    protected = list(source)
    names: set[str] = set()
    block_restore: dict[int, str] = {}
    code_boundaries: set[str] = set()
    raw_block_openers: set[str] = set()
    inline_boundaries: set[str] = set()
    for token in tokens:
        if token.map is None:
            continue
        first, last = token.map
        start, end = offsets[first], offsets[min(last, len(offsets) - 1)]
        if token.type == "inline":
            # Image HTML contributes only alt text. Preserve opaque tag attributes,
            # while leaving the alt's visible prose markers available for cleanup.
            for position, char in _image_html_positions(
                token, source_lines, offsets
            ).items():
                if position >= mask_start:
                    protected[position] = image_masks[char]
        if token.type in ("code_block", "fence"):
            for pos in range(max(start, mask_start), end):
                if protected[pos] in masks:
                    protected[pos] = masks[protected[pos]]
            if start >= mask_start and start < end:
                # Only parser-confirmed code gets a boundary marker. A candidate
                # inside a quote paragraph may instead be a valid inline span.
                boundary = chr(
                    next(code for code in candidates if chr(code) not in present)
                )
                protected[start] = boundary
                block_restore[ord(boundary)] = source[start]
                code_boundaries.add(boundary)
            continue
        if token.type == "html_block" and _HTML_RAW_BLOCK_HEAD.match(
            token.content.lstrip(" \t")
        ):
            opening = _HTML_RAW_BLOCK_HEAD.search(source, start, end)
            if opening is not None and opening.start() >= mask_start:
                marker = chr(
                    next(code for code in candidates if chr(code) not in present)
                )
                protected[opening.start()] = marker
                block_restore[ord(marker)] = "<"
                raw_block_openers.add(marker)
            continue
        if (
            token.type in ("inline", "hr", "blockquote_open", "list_item_open")
            and start >= mask_start
            and start < end
        ):
            # Unlike protected code, a new inline block must still lex its real
            # first character after it has stopped any earlier pending span.
            marker = chr(next(code for code in candidates if chr(code) not in present))
            protected[start] = marker
            block_restore[ord(marker)] = source[start]
            inline_boundaries.add(marker)
        if token.type != "definition":
            continue
        name = _reference_name(token.meta["label"])
        if name:
            names.add(name)
        opening = source.find("[", start, end)
        if opening < 0:
            continue
        closing = _reference_label_end(source[opening + 1 : end])
        if closing is None:
            continue
        label_end = opening + 1 + closing
        for pos in range(max(opening + 1, mask_start), end):
            char = protected[pos]
            if pos == label_end:
                continue
            if char in masks and (pos > label_end or char not in "!="):
                protected[pos] = masks[char]
    restore = {ord(mask): char for char, mask in masks.items()}
    image_restore = {ord(mask): char for char, mask in image_masks.items()}
    restore.update(image_restore)
    restore.update(block_restore)
    return (
        "".join(protected),
        frozenset(names),
        restore,
        frozenset(code_boundaries),
        frozenset(raw_block_openers),
        frozenset(inline_boundaries),
        image_restore,
    )


def _link_suffix_end(
    text: str,
    start: int,
    state: _LinkSuffix,
    *,
    final: bool,
    code_boundaries: frozenset[str] = frozenset(),
    raw_block_openers: frozenset[str] = frozenset(),
    inline_boundaries: frozenset[str] = frozenset(),
) -> tuple[int | None, int | None]:
    """Recognize link metadata without rescanning a long destination or title."""
    maximum = _inline_boundary(
        text,
        start,
        state.position,
        code_boundaries,
        raw_block_openers,
        inline_boundaries,
    )
    while start + state.position < maximum:
        pos = start + state.position
        char = text[pos]
        if state.stage in ("angle", "bare", "title") and char == "\\":
            if pos + 1 >= maximum:
                break
            following = text[pos + 1]
            if state.stage == "bare" and following in " \t\n":
                return None, None
            state.position += 2 if following in punctuation else 1
            continue
        if state.stage == "open":
            if char != (":" if state.reference else "("):
                return None, None
            state.position += 1
            state.stage = "leading"
        elif state.stage == "leading":
            if char in " \t\n":
                state.position += 1
            elif char == ")" and not state.reference:
                return pos + 1, 0
            elif char == "<":
                state.position += 1
                state.stage = "angle"
            else:
                state.stage = "bare"
        elif state.stage == "angle":
            if char in "<\n":
                return None, None
            state.position += 1
            if char == ">":
                state.stage = "destination-end"
        elif state.stage == "bare":
            if char in " \t\n":
                if state.depth:
                    return None, None
                state.stage = "destination-end"
            elif char == ")" and state.depth == 0:
                return (None, None) if state.reference else (pos + 1, 0)
            else:
                if char == "(":
                    state.depth += 1
                    if state.depth > 32:
                        return None, None
                elif char == ")":
                    state.depth -= 1
                elif ord(char) < 32 or ord(char) == 127:
                    return None, None
                state.position += 1
        elif state.stage == "destination-end":
            if state.reference and char == "\n":
                state.position += 1
                state.reference_end = state.position
                state.stage = "reference-title"
            elif char in " \t\n":
                state.separated = True
                state.position += 1
            elif char == ")" and not state.reference:
                return pos + 1, 0
            elif state.separated and char in "\"'(":
                state.closer = ")" if char == "(" else char
                state.position += 1
                state.stage = "title"
            else:
                return None, None
        elif state.stage == "reference-title":
            if char in " \t":
                state.position += 1
            elif char in "\"'(":
                state.closer = ")" if char == "(" else char
                state.position += 1
                state.stage = "title"
            else:
                return start + state.reference_end, 0
        elif state.stage == "title":
            if state.closer == ")" and char == "(":
                if state.reference_end:
                    return start + state.reference_end, 0
                return None, None
            state.position += 1
            if char == state.closer:
                state.stage = "title-end"
        elif state.reference and char == "\n":
            return pos + 1, 0
        elif char in " \t\n":
            state.position += 1
        else:
            if state.reference_end:
                return start + state.reference_end, 0
            return (pos + 1, 0) if char == ")" and not state.reference else (None, None)
    if state.reference and (final or maximum < len(text)):
        if state.stage == "title-end":
            return maximum, 0
        if state.reference_end:
            return start + state.reference_end, 0
        if state.stage in ("destination-end", "title-end") or (
            state.stage == "bare" and state.depth == 0
        ):
            return maximum, 0
    unfinished = state.position if not final and maximum == len(text) else None
    return None, unfinished


def _tag_end(text: str, start: int) -> int | None:
    """Find an HTML tag's end without treating a quoted '>' as its end."""
    quote: str | None = None
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char == ">":
            return index + 1
    return None


class _AnnotationEncoding(HTMLParser):
    """Read annotation-xml's effective encoding using the standard HTML attribute parser."""

    html_children = False

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Honor the first encoding attribute, as the HTML tokenizer does."""
        for name, value in attrs:
            if name == "encoding":
                self.html_children = (value or "").lower() in (
                    "text/html",
                    "application/xhtml+xml",
                )
                break


@dataclass
class _ForeignElement:
    """One explicit namespace scope under an SVG or MathML ancestor."""

    name: str
    namespace: str
    html_integration: bool = False
    text_integration: bool = False


def _opens_raw_text(tag: str, namespace: str, self_closing: bool) -> bool:
    """Keep HTML raw-text behavior while honoring foreign self-closing elements."""
    return tag in _RAW_TEXT_END and not (
        namespace != "html"
        and (self_closing or (namespace == "svg" and tag == "title"))
    )


class _MarkerCleaner:
    """Stream markers away, stopping only at reference labels needing future definitions."""

    def __init__(
        self,
        references: frozenset[str] | None = None,
        definition_restore: dict[int, str] | None = None,
        code_boundaries: frozenset[str] = frozenset(),
        raw_block_openers: frozenset[str] = frozenset(),
        inline_boundaries: frozenset[str] = frozenset(),
        image_restore: dict[int, str] | None = None,
    ) -> None:
        """Start with nothing buffered and no code fence open."""
        self._line = ""
        # Classification needs the whole source line even after partial output was streamed.
        self._released_line_parts: list[str] = []
        self._line_had_html_context = False
        self._released_some_of_line = False
        # The fence that opened the code block we are in: its character and length, or None.
        self._fence: tuple[str, int] | None = None
        self._indented_code = False
        self._can_start_indented = True
        self._raw_tag: str | None = None
        self._raw_block = False
        # A tag/comment or raw-text closing tag may be split between chunks.
        self._html_tail = ""
        self._inline_tail = ""
        self._inline_scanned: int | None = 0
        self._labels: list[_LinkLabel] = []
        self._next_reference: _LinkLabel | None = None
        self._references = references
        self._definition_restore = definition_restore or {}
        self._code_boundaries = code_boundaries
        self._raw_block_openers = raw_block_openers
        self._inline_boundaries = inline_boundaries
        self._image_restore = image_restore or {}
        image_characters = {chr(code) for code in self._image_restore}
        self._prose_special = (
            re.compile(
                _PROSE_SPECIAL.pattern[:-1]
                + "".join(raw_block_openers | inline_boundaries | image_characters)
                + "]"
            )
            if raw_block_openers or inline_boundaries or image_characters
            else _PROSE_SPECIAL
        )
        self.needs_references = False
        self.reference_tail_size = 0
        self._image_pending = False
        self._link_suffix: _LinkSuffix | None = None
        self._replay_source: str | None = None
        self._backslashes = 0
        self._at_line_start = True
        self._line_indent = 0
        self._html_block_tag: str | None = None
        self._html_block_depth = 0
        # Namespace scopes are independent of the visual's outer HTML root.
        # Ordinary HTML outside an SVG or MathML ancestor needs no element stack.
        self._foreign_context: list[_ForeignElement] = []

    def _foreign_namespace(self, name: str) -> str:
        """Apply the SVG and MathML integration-point rules to one explicit child."""
        namespace = "html"
        if self._foreign_context:
            parent = self._foreign_context[-1]
            namespace = parent.namespace
            if (
                parent.html_integration
                or (parent.text_integration and name not in ("mglyph", "malignmark"))
                or (
                    namespace == "math"
                    and parent.name == "annotation-xml"
                    and name == "svg"
                )
            ):
                namespace = "html"
        return name if namespace == "html" and name in ("svg", "math") else namespace

    def _track_foreign_namespace(
        self, name: str, source: str, *, opening: bool, self_closing: bool
    ) -> str:
        """Track only explicit namespace scopes while a foreign ancestor is open."""
        namespace = self._foreign_namespace(name)
        if opening:
            if not self._foreign_context and namespace == "html":
                return namespace
            html_void = namespace == "html" and name in (
                "area",
                "base",
                "br",
                "col",
                "embed",
                "hr",
                "img",
                "input",
                "link",
                "meta",
                "param",
                "source",
                "track",
                "wbr",
            )
            if not (
                (self_closing and namespace != "html")
                or html_void
                or _opens_raw_text(name, namespace, self_closing)
            ):
                html_integration = namespace == "svg" and name in (
                    "foreignobject",
                    "desc",
                    "title",
                )
                if namespace == "math" and name == "annotation-xml":
                    annotation = _AnnotationEncoding()
                    annotation.feed(source)
                    html_integration = annotation.html_children
                self._foreign_context.append(
                    _ForeignElement(
                        name,
                        namespace,
                        html_integration,
                        namespace == "math"
                        and name in ("mi", "mo", "mn", "ms", "mtext"),
                    )
                )
        else:
            for index in range(len(self._foreign_context) - 1, -1, -1):
                if self._foreign_context[index].name == name:
                    del self._foreign_context[index:]
                    break
        return namespace

    def _emit(self, out: list[str], source: str, *, prose: bool = False) -> None:
        """Track the output line position, including HTML wrapped in removed markers."""
        emitted = _MARKERS.sub("", source) if prose else source
        out.append(emitted)
        for label in self._labels:
            if label.source is not None:
                label.source = (
                    label.source + source
                    if len(label.source) + len(source) <= 999
                    else None
                )
        if emitted.strip(" \t\n"):
            for label in self._labels:
                label.content = True
        if "\n" in emitted:
            last = emitted.rsplit("\n", 1)[1]
            self._at_line_start = not last.strip(" \t")
            self._line_indent = len(last.expandtabs(4)) if self._at_line_start else 0
        elif emitted.strip(" \t"):
            self._at_line_start = False
        elif self._at_line_start:
            self._line_indent += len(emitted.expandtabs(4))

    def feed(self, text: str) -> str:
        """Return `text` with markers removed, less any tail that might still become one."""
        if not text:
            return ""
        out: list[str] = []
        while True:
            self._line += text
            while "\n" in self._line:
                line, self._line = self._line.split("\n", 1)
                out.append(self._complete_line(line))
                self._released_some_of_line = False
                if self.needs_references:
                    return "".join(out)
                if self._inline_scanned is None or self._replay_source is not None:
                    break
            if self._inline_scanned is not None and self._replay_source is None:
                head, held = self._split_partial(self._line)
                self._line = held
                if head:
                    self._released_line_parts.append(head)
                    self._released_some_of_line = True
                    if self._fence:
                        self._emit(out, head)
                    else:
                        self._line_had_html_context |= (
                            self._raw_block
                            or self._html_block_tag is not None
                            or self._in_opaque_block()
                        )
                        out.append(self._filter_html(head))
                        if self.needs_references:
                            return "".join(out)
            if self._replay_source is not None:
                text = self._replay_source + self._line
                self._replay_source = None
                self._line = ""
                self._released_some_of_line = False
                continue
            if self._inline_scanned is not None or not self._inline_tail:
                break
            # A block boundary proves the opener is unmatched. Replay now so
            # streaming resumes, keeping any held marker/fence suffix last.
            pending, self._inline_tail = self._inline_tail, ""
            self._inline_scanned = 0
            opening_end = self._pending_opener_end(pending)
            self._emit(out, pending[:opening_end])
            text = pending[opening_end:] + self._line
            self._line = ""
            self._released_some_of_line = True
        return "".join(out)

    def flush(self, source: str = "") -> str:
        """Release what was held back, because no more text is coming."""
        html_blocks: list[tuple[int, int]] | None = None

        def keep_html_tail(tail: str) -> bool:
            nonlocal html_blocks
            if (
                self._raw_tag is not None
                or self._html_block_tag is not None
                or tail[:1] in self._raw_block_openers
            ):
                return True
            head = _HTML_TAG_HEAD.match(tail)
            if (
                head is not None
                and head.group(1).lower() == "svg"
                and not tail.startswith("</")
            ):
                # The downstream formatter recognizes SVG after introductory prose too.
                return True
            if html_blocks is None:
                html_blocks = [
                    (token.map[0], token.map[1])
                    for token in MarkdownIt("commonmark").parse(source)
                    if token.type == "html_block" and token.map is not None
                ]
            prefix = source[: len(source) - len(tail)]
            line = prefix.replace("\r\n", "\n").replace("\r", "\n").count("\n")
            return any(first <= line < last for first, last in html_blocks)

        out = [self._flush_buffer(keep_html_tail)]
        while not self.needs_references and (
            self._inline_tail or self._replay_source is not None
        ):
            if self._replay_source is not None:
                replay, self._replay_source = self._replay_source, None
                out.append(self.feed(replay))
                out.append(self._flush_buffer(keep_html_tail))
                continue
            # An unmatched opener is ordinary Markdown text. Replay its remainder
            # so real HTML, later code spans, and whole-line fences still work.
            pending, self._inline_tail = self._inline_tail, ""
            self._inline_scanned = 0
            opening_end = self._pending_opener_end(pending)
            self._emit(out, pending[:opening_end])
            self._released_some_of_line = True
            out.append(self.feed(pending[opening_end:]))
            out.append(self._flush_buffer(keep_html_tail))
        return "".join(out)

    def _pending_opener_end(self, pending: str) -> int:
        """Release one failed link bracket or an unmatched backtick run."""
        if pending.startswith("]"):
            label = self._labels.pop()
            self._next_reference = label if label.active else None
            if label.image and label.contains_link:
                label.restore_outer = tuple(
                    (ancestor, ancestor.active, ancestor.contains_link)
                    for ancestor in self._labels
                )
                self._disable_outer_links()
            self._link_suffix = None
            return 1
        return _run_end(pending, 0)

    def _disable_outer_links(self) -> None:
        """Stop nested links at the nearest image alt label."""
        for label in reversed(self._labels):
            if label.image:
                label.contains_link = True
                break
            label.active = False

    def _flush_buffer(self, keep_html_tail: Callable[[str], bool]) -> str:
        """Finish buffered source, allowing a code span to close at end of stream."""
        whole_line = not self._released_some_of_line
        tail, self._line = self._line, ""
        self._released_line_parts.clear()
        self._line_had_html_context = False
        self._released_some_of_line = False
        if whole_line and self._needs_block_parse(tail):
            self.needs_references = True
            self.reference_tail_size = len(tail)
            return ""
        # A fragment that never became a marker is text, and is shown as it is.
        out = (
            tail
            if self._fence or (whole_line and self._starts_indented_code(tail))
            else self._filter_html(tail, final=True)
        )
        html_tail, self._html_tail = self._html_tail, ""
        if html_tail and not keep_html_tail(html_tail):
            # An unfinished inline tag is literal Markdown. Release just its first
            # character so later code spans and real HTML are replayed normally.
            released = [out]
            self._emit(released, html_tail[:1])
            self._replay_source = html_tail[1:]
            self._released_some_of_line = True
            return "".join(released)
        return out + html_tail

    def _inside_literal(self) -> bool:
        """Keep Markdown block rules outside HTML and unfinished inline syntax."""
        return (
            self._raw_tag is not None
            or self._html_block_tag is not None
            or bool(self._html_tail or self._inline_tail)
        )

    def _in_opaque_block(self) -> bool:
        """Remember a leading declaration when its last line arrives in fragments."""
        return (
            self._at_line_start
            and self._line_indent <= 3
            and any(self._html_tail.startswith(opener) for opener in _HTML_OPAQUE)
        )

    def _starts_indented_code(self, text: str) -> bool:
        """Recognize four-column code indentation outside a prose paragraph."""
        return (
            not self._inside_literal()
            and (self._indented_code or self._can_start_indented)
            and _CODE_INDENT.match(text) is not None
        )

    def _needs_block_parse(self, text: str) -> bool:
        """Defer ambiguous container code while keeping HTML visuals on their existing path."""
        return (
            self._references is None
            and self._fence is None
            and not self._inside_literal()
            and (
                _container_code_candidate(text)
                or _container_raw_block_candidate(text)
                or (
                    _CODE_INDENT.match(text) is not None
                    and bool(text.strip(" \t"))
                    and not _FENCE_LINE.match(text)
                    and not self._starts_indented_code(text)
                )
            )
        )

    def _complete_line(self, line: str) -> str:
        source = "".join(self._released_line_parts) + line
        self._released_line_parts.clear()
        html_context = self._line_had_html_context
        self._line_had_html_context = False
        whole_line = not self._released_some_of_line
        if whole_line and self._needs_block_parse(line):
            self.needs_references = True
            self.reference_tail_size = len(line) + 1 + len(self._line)
            return ""
        if self._fence is not None:
            if whole_line and self._closes_fence(line):
                self._fence = None
            self._at_line_start = True
            self._line_indent = 0
            self._can_start_indented = self._fence is None
            return line + "\n"
        if not whole_line:
            # Indented code lines are held whole. Released source already ended
            # that block, even if an inline HTML tag is still buffered now.
            self._indented_code = False
        in_literal = self._inside_literal()
        if whole_line and not in_literal:
            if self._indented_code and not line.strip(" \t"):
                self._at_line_start = True
                self._line_indent = 0
                return line + "\n"
            if self._starts_indented_code(line):
                self._labels.clear()
                self._indented_code = True
                self._at_line_start = True
                self._line_indent = 0
                return line + "\n"
        if not in_literal:
            self._indented_code = False
        if whole_line and not in_literal and not line.strip(" \t"):
            self._labels.clear()
        if whole_line and not in_literal:
            opening = _CODE_FENCE_OPEN.match(line)
            if opening:
                self._labels.clear()
                run = opening.group(1)
                self._fence = (run[0], len(run))
                self._can_start_indented = False
                return line + "\n"
        if whole_line and not in_literal and _FENCE_LINE.match(line):
            # The fence line itself: not content. Its newline goes too, or every fenced block
            # would gain a blank line.
            self._labels.clear()
            self._can_start_indented = True
            return ""
        classification = _MARKERS.sub("", source)
        block_head = block_html_open_re.match(classification)
        leading_raw = _raw_block_head(classification)
        html_block = (
            html_context
            or self._raw_block
            or self._html_block_tag is not None
            or self._in_opaque_block()
            or (
                block_head is not None
                and block_head.group(1).lower() not in _RAW_TEXT_END
            )
            or leading_raw
            or _HTML_ROOT_HEAD.match(classification.lstrip(" \t"))
            or _HTML_DOCTYPE_HEAD.match(classification.lstrip(" \t"))
            or any(
                classification.lstrip(" \t").startswith(opener)
                for opener in _HTML_OPAQUE
            )
        )
        out = self._filter_html(line + "\n")
        self._can_start_indented = (
            not source.strip(" \t")
            or heading_re.match(classification) is not None
            or bool(
                html_block and self._raw_tag is None and self._html_block_tag is None
            )
        )
        return out

    def _filter_html(self, text: str, *, final: bool = False) -> str:
        """Strip prose markers while preserving actual HTML and Markdown code spans."""
        had_inline = bool(self._inline_tail)
        text = self._inline_tail + self._html_tail + text
        self._html_tail = ""
        self._inline_tail = ""
        if (
            had_inline
            and self._references is None
            and _has_block_candidate(text, self._inline_scanned or 0)
        ):
            # The parser distinguishes real new blocks from continuation lines
            # within this same paragraph's inline code or link.
            self.needs_references = True
            self.reference_tail_size = len(text) + len(self._line)
            return ""
        out: list[str] = []
        index = 0
        while index < len(text):
            if self._raw_tag is not None:
                # A real HTML parent controls its body even when the Markdown block parser
                # found a definition there. Keep the masked view for text after its closer.
                raw_text = (
                    text.translate(self._definition_restore)
                    if self._definition_restore
                    else text
                )
                prose = self._raw_tag not in ("script", "style")
                match = _RAW_TEXT_END[self._raw_tag].search(raw_text, index)
                if match is None:
                    # Keep only a possible closing-tag prefix; stream all other code.
                    last_lt = raw_text.rfind("<", index)
                    closer = f"</{self._raw_tag}"
                    if last_lt >= index and closer.startswith(
                        raw_text[last_lt:].lower()
                    ):
                        self._emit(out, raw_text[index:last_lt], prose=prose)
                        self._html_tail = raw_text[last_lt:]
                    else:
                        self._emit(out, raw_text[index:], prose=prose)
                    break
                end = _tag_end(raw_text, match.end())
                if end is None:
                    self._emit(out, raw_text[index : match.start()], prose=prose)
                    self._html_tail = raw_text[match.start() :]
                    break
                self._emit(out, raw_text[index : match.start()], prose=prose)
                self._emit(out, raw_text[match.start() : end])
                self._raw_tag = None
                self._raw_block = False
                index = end
                continue

            special = self._prose_special.search(text, index)
            if special is None:
                tail = text[index:]
                if tail:
                    self._next_reference = None
                self._image_pending = tail.endswith("!") and (
                    len(tail) > 1 or self._backslashes % 2 == 0
                )
                self._emit(out, text[index:], prose=True)
                self._backslashes = 0
                break
            start = special.start()
            prefix = text[index:start]
            if prefix:
                self._next_reference = None
                self._image_pending = prefix.endswith("!") and (
                    len(prefix) > 1 or self._backslashes % 2 == 0
                )
            self._emit(out, text[index:start], prose=True)
            if start > index:
                self._backslashes = 0
            char = text[start]
            if ord(char) in self._image_restore:
                if self._html_block_tag is not None:
                    # Actual visuals outrank the block parser's image metadata.
                    text = (
                        text[:start]
                        + self._image_restore[ord(char)]
                        + text[start + 1 :]
                    )
                    index = start
                    continue
                self._emit(out, char)
                index = start + 1
                continue
            if char in self._inline_boundaries:
                # Keep the first source character visible to the normal lexer:
                # it may itself open inline code, HTML, a link, or an escape.
                original = self._definition_restore[ord(char)]
                text = text[:start] + original + text[start + 1 :]
                index = start
                continue
            if char in self._raw_block_openers:
                end = _tag_end(text, start + 1)
                if end is None:
                    self._html_tail = text[start:]
                    break
                # This opener has full-turn CommonMark block provenance, even
                # when its container prefix or attributes are not inline HTML.
                raw_tag = text[start + 1 : end].split(maxsplit=1)[0].rstrip(">").lower()
                namespace = self._foreign_namespace(raw_tag)
                if _opens_raw_text(raw_tag, namespace, text[start:end].endswith("/>")):
                    self._raw_tag = raw_tag
                    self._raw_block = namespace == "html"
                self._emit(out, "<" + text[start + 1 : end])
                index = end
                continue
            if self._html_block_tag is not None and char in ("\\", "`", "[", "]", "!"):
                # Markdown escapes/code spans do not apply inside an HTML visual.
                end = _run_end(text, start)
                self._emit(out, text[start:end])
                index = end
                continue
            if char == "\\":
                self._next_reference = None
                self._image_pending = False
                end = _run_end(text, start)
                self._emit(out, text[start:end])
                self._backslashes += end - start
                index = end
                continue
            escaped = self._backslashes % 2 == 1
            self._backslashes = 0
            if escaped:
                self._next_reference = None
                self._image_pending = False
                self._emit(out, char)
                index = start + 1
                continue
            if char == "[":
                label = _LinkLabel(
                    image=self._image_pending,
                    full_reference=self._next_reference is not None,
                    reference_image=(
                        self._next_reference.image
                        if self._next_reference is not None
                        else False
                    ),
                    restore_outer=(
                        self._next_reference.restore_outer
                        if self._next_reference is not None
                        else ()
                    ),
                    reference=(
                        not self._labels
                        and not self._image_pending
                        and self._at_line_start
                        and self._line_indent <= 3
                    ),
                )
                self._next_reference = None
                self._image_pending = False
                self._emit(out, char)
                self._labels.append(label)
                index = start + 1
                continue
            self._next_reference = None
            self._image_pending = False
            if char == "]":
                if not self._labels or not self._labels[-1].active:
                    if self._labels:
                        self._labels.pop()
                    self._emit(out, char)
                    index = start + 1
                    continue
                label = self._labels[-1]
                if (
                    self._references is None
                    and not label.reference
                    and not label.image
                    and label.content
                    and label.source is not None
                    and _reference_label_end(label.source + "]") == len(label.source)
                    and text[start + 1 : start + 2] == ":"
                ):
                    # A quote/list prefix may hide a real definition from this local scanner.
                    # Wait before emitting its metadata; the final block parser decides validity.
                    self.needs_references = True
                    self.reference_tail_size = len(text) - start + len(self._line)
                    break
                if self._link_suffix is None:
                    self._link_suffix = _LinkSuffix()
                if (
                    self._link_suffix.stage == "open"
                    and self._labels[-1].reference
                    and self._labels[-1].content
                    and text[start + 1 : start + 2] == ":"
                ):
                    self._link_suffix.reference = True
                end, self._inline_scanned = _link_suffix_end(
                    text,
                    start,
                    self._link_suffix,
                    final=final,
                    code_boundaries=self._code_boundaries,
                    raw_block_openers=self._raw_block_openers,
                    inline_boundaries=self._inline_boundaries,
                )
                if end is None:
                    self._inline_tail = text[start:]
                    break
                label = self._labels.pop()
                if not label.image:
                    self._disable_outer_links()
                reference = self._link_suffix.reference
                self._link_suffix = None
                self._emit(out, text[start:end])
                if reference and end < len(text):
                    self._replay_source = text[end:]
                    break
                index = end
                continue
            if char == "`":
                end, self._inline_scanned = _code_span_end(
                    text,
                    start,
                    self._inline_scanned,
                    final=final,
                    code_boundaries=self._code_boundaries,
                    raw_block_openers=self._raw_block_openers,
                    inline_boundaries=self._inline_boundaries,
                )
                if end is None:
                    self._inline_tail = text[start:]
                    break
                self._emit(out, text[start:end])
                index = end
                continue
            if self._references is None and any(label.image for label in self._labels):
                # Native image parsing decides whether this HTML-looking label is inert alt
                # metadata, including descriptions longer than the reference-label limit.
                self.needs_references = True
                self.reference_tail_size = len(text) - start + len(self._line)
                break
            fragment = text[start:]
            opaque = next(
                (opener for opener in _HTML_OPAQUE if fragment.startswith(opener)),
                None,
            )
            if opaque is not None:
                closer = _HTML_OPAQUE[opaque]
                end = text.find(closer, start + len(opaque))
                end = end + len(closer) if end >= 0 else None
                match = None
                tag = None
            elif "<!DOCTYPE".startswith(fragment.upper()) or _HTML_DOCTYPE_HEAD.match(
                fragment
            ):
                end = _tag_end(text, start + 2)
                match = None
                tag = None
            else:
                match = _HTML_TAG_HEAD.match(text, start)
                if match is None:
                    if (
                        fragment in ("<", "</")
                        or any(opener.startswith(fragment) for opener in _HTML_OPAQUE)
                        or _HTML_TAG_PREFIX.fullmatch(fragment)
                    ):
                        self._html_tail = fragment
                        break
                    self._emit(out, "<")
                    index = start + 1
                    continue
                if (
                    not fragment.startswith("</")
                    and match.group(1).lower() in _RAW_TEXT_END
                    and self._labels
                    and self._labels[-1].source is not None
                    and _reference_label_end(self._labels[-1].source + "]")
                    == len(self._labels[-1].source)
                ):
                    if self._references is None:
                        # A future definition can make this HTML-looking source reference metadata.
                        # The wrapper finishes only this ambiguous suffix once the turn ends.
                        self.needs_references = True
                        # _line also contains any held marker tail or later complete source lines.
                        self.reference_tail_size = len(text) - start + len(self._line)
                        break
                    protected_end = self._resolved_reference_end(
                        text, start, final=final
                    )
                    if protected_end == -1:
                        self._inline_tail = text[start:]
                        self._inline_scanned = 0
                        break
                    if protected_end is not None:
                        label = self._labels.pop()
                        self._emit(out, text[start : protected_end + 1], prose=True)
                        for ancestor, active, contains_link in label.restore_outer:
                            ancestor.active = active
                            ancestor.contains_link = contains_link
                        if not label.reference_image:
                            self._disable_outer_links()
                        index = protected_end + 1
                        continue
                end = _tag_end(text, match.end())
                tag = match.group(1).lower() if not fragment.startswith("</") else None
            if end is None:
                self._html_tail = fragment
                break
            if (
                tag in _RAW_TEXT_END
                and self._html_block_tag is None
                and not HTML_OPEN_CLOSE_TAG_RE.fullmatch(text[start:end])
                and not (
                    self._at_line_start
                    and self._line_indent <= 3
                    and _HTML_RAW_BLOCK_HEAD.match(fragment)
                )
            ):
                # Inline HTML requires valid attributes. HTML blocks and visuals instead
                # reach the browser as raw source, including recoverable malformed tags.
                self._emit(out, "<")
                index = start + 1
                continue
            if match is not None:
                name = match.group(1).lower()
                self_closing = text[start:end].endswith("/>")
                namespace = self._track_foreign_namespace(
                    name,
                    text[start:end],
                    opening=tag is not None,
                    self_closing=self_closing,
                )
                self_closing_svg = tag == "svg" and self_closing
                if self._html_block_tag == name and not self_closing_svg:
                    self._html_block_depth += -1 if tag is None else 1
                    if self._html_block_depth == 0:
                        self._html_block_tag = None
                elif (
                    self._html_block_tag is None
                    and not self_closing_svg
                    and (self._at_line_start or tag == "svg")
                    and tag not in _RAW_TEXT_END
                    and tag is not None
                    and (
                        block_html_open_re.match(fragment)
                        or tag in ("html", "body", "svg")
                    )
                ):
                    # Use the same block tags as the downstream StreamFormatter.
                    self._html_block_tag = tag
                    self._html_block_depth = 1
                    self._labels.clear()
            leading_metadata = match is None and self._at_line_start
            opens_raw_text = tag in _RAW_TEXT_END and _opens_raw_text(
                tag, namespace, self_closing
            )
            if opens_raw_text:
                self._raw_block = (
                    self._at_line_start
                    and self._line_indent <= 3
                    and _raw_block_head(fragment)
                )
            self._emit(out, text[start:end])
            if leading_metadata:
                # Leading HTML metadata may precede the visual's root on this line.
                self._at_line_start = True
            if opens_raw_text:
                # HTML raw-text elements remain non-void even with self-closing syntax.
                self._raw_tag = tag
            index = end
        return "".join(out)

    def _resolved_reference_end(
        self, text: str, start: int, *, final: bool
    ) -> int | None:
        """Protect only a defined full-reference's second label, never its visible label."""
        label = self._labels[-1]
        if not label.full_reference or label.source is None:
            return None
        source = label.source + text[start:]
        end = _reference_label_end(source)
        if end is None:
            if (
                not final
                and len(source) <= 999
                and _reference_label_end(source + "]") == len(source)
                and _inline_boundary(
                    source,
                    0,
                    0,
                    self._code_boundaries,
                    self._raw_block_openers,
                    self._inline_boundaries,
                )
                == len(source)
            ):
                return -1
            return None
        if _reference_name(source[:end]) not in self._references:
            return None
        return start + end - len(label.source)

    def _split_partial(self, text: str) -> tuple[str, str]:
        """Split an unfinished line into what can go out now and what must wait."""
        if not text:
            return "", ""
        if not self._released_some_of_line and _MAY_BE_FENCE.match(text):
            return "", text
        if not self._released_some_of_line and self._starts_indented_code(text):
            return "", text
        if (
            not self._released_some_of_line
            and not self._inside_literal()
            and self._fence is None
            and (_CONTAINER_PREFIX.match(text) or self._needs_block_parse(text))
        ):
            return "", text
        if self._fence is not None:
            return text, ""
        match = _PARTIAL_TAIL.search(text)
        return text[: match.start()], text[match.start() :]

    def _closes_fence(self, line: str) -> bool:
        closing = _CODE_FENCE_CLOSE.match(line)
        if closing is None or self._fence is None:
            return False
        run = closing.group(1)
        char, length = self._fence
        return run[0] == char and len(run) >= length


class PreserveMarkerFilter:
    """Stream normally; resolve rare reference or Markdown block ambiguity at turn end."""

    def __init__(self) -> None:
        """Keep external source separate from the cleaner's internal source replays."""
        self._cleaner = _MarkerCleaner()
        self._source: list[str] = []
        self._source_size = 0
        self._reference_offset: int | None = None
        self._emitted: list[str] = []
        self._finished = False

    def feed(self, text: str) -> str:
        """Clean ordinary chunks immediately, holding only an ambiguous reference suffix."""
        if not text:
            return ""
        self._source.append(text)
        self._source_size += len(text)
        self._finished = False
        if self._cleaner.needs_references:
            return ""
        out = self._cleaner.feed(text)
        if self._cleaner.needs_references:
            self._reference_offset = (
                self._source_size - self._cleaner.reference_tail_size
            )
        self._emitted.append(out)
        return out

    def flush(self) -> str:
        """Use actual definitions to distinguish reference metadata from real HTML."""
        if self._finished:
            return ""
        original_source = "".join(self._source)
        out = (
            ""
            if self._cleaner.needs_references
            else self._cleaner.flush(original_source)
        )
        if self._cleaner.needs_references:
            if self._reference_offset is None:
                self._reference_offset = (
                    self._source_size - self._cleaner.reference_tail_size
                )
            (
                source,
                references,
                restore,
                code_boundaries,
                raw_block_openers,
                inline_boundaries,
                image_restore,
            ) = _reference_replay_source(original_source, self._reference_offset)
            cleaner = _MarkerCleaner(
                references,
                restore,
                code_boundaries,
                raw_block_openers,
                inline_boundaries,
                image_restore,
            )
            complete = (
                cleaner.feed(source) + cleaner.flush(original_source)
            ).translate(restore)
            emitted = "".join(self._emitted)
            if not complete.startswith(emitted):
                message = "Reference replay changed text already streamed"
                raise ValueError(message)
            out = complete[len(emitted) :]
        self._emitted.append(out)
        self._finished = True
        return out
