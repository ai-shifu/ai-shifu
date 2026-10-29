"""Physical Markdown block boundaries with original source offsets."""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern
from string import punctuation
from typing import Literal

COMPILED_PHYSICAL_LINE_END_REGEX = re.compile(r"\r\n|\r|\n")
COMPILED_CONTAINER_LIST_REGEX = re.compile(r"(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t]|$)")
COMPILED_DOCUMENT_FENCE_REGEX = re.compile(r"(`{3,})([^`]*$)|(~{3,})(.*$)")
COMPILED_DOCUMENT_TAG_REGEX = re.compile(
    r" {0,3}</?([A-Za-z][A-Za-z0-9-]*)(?=[ \t/>]|$)"
)


COMPILED_REFERENCE_PREFIX_REGEX = re.compile(
    r" {0,3}\[((?:\\[^\r\n]|[^\[\]\\\r\n])+)]\:[ \t]*"
)
COMPILED_ATX_START_REGEX = re.compile(r" {0,3}#{1,6}(?=[ \t]|$)")
COMPILED_DOCUMENT_BREAK_REGEX = re.compile(
    r" {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"
)
COMPILED_SETEXT_REGEX = re.compile(r" {0,3}(?:=+|-+)[ \t]*$")
COMPILED_REFERENCE_HTML_BREAK_REGEX = re.compile(
    r" {0,3}(?:<!--|<\?|<!\[CDATA\[|<![A-Z])"
)

HTML_BLOCK_TAGS = frozenset(
    [
        "address",
        "article",
        "aside",
        "base",
        "basefont",
        "blockquote",
        "body",
        "caption",
        "center",
        "col",
        "colgroup",
        "dd",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "frame",
        "frameset",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hr",
        "html",
        "iframe",
        "legend",
        "li",
        "link",
        "main",
        "menu",
        "menuitem",
        "nav",
        "noframes",
        "ol",
        "optgroup",
        "option",
        "p",
        "param",
        "search",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "title",
        "tr",
        "track",
        "ul",
    ]
)


_EMAIL_LOCAL = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.!#$%&'*+/=?^_`{|}~-"
)
_ASCII_ALNUM = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


def read_angle_autolink(text: str, start: int, *, partial: bool = False) -> int | None:
    """Read a native URI/email angle link, or a viable EOF prefix for streams."""
    if start >= len(text) or text[start] != "<":
        return None
    uri = email = True
    scheme_size = 0
    uri_body = False
    email_domain = False
    local_size = label_size = 0
    label_alnum = False
    at = start + 1
    while at < len(text):
        character = text[at]
        if character == ">":
            return (
                at + 1
                if (uri and uri_body)
                or (email and email_domain and label_size and label_alnum)
                else None
            )
        if uri:
            if uri_body:
                # Native Markdown normalization admits NUL as a replacement character;
                # source offsets and raw variable text remain untouched.
                uri = (
                    character != "<"
                    and (ord(character) > 32 or character == "\x00")
                    and character != "\x7f"
                )
            elif character == ":":
                uri = 2 <= scheme_size <= 32
                uri_body = uri
            elif character.isascii() and (
                character.isalpha()
                or (scheme_size > 0 and (character.isdigit() or character in "+.-"))
            ):
                scheme_size += 1
                uri = scheme_size <= 32
            else:
                uri = False
        if email:
            if not email_domain:
                if character in _EMAIL_LOCAL:
                    local_size += 1
                elif character == "@" and local_size:
                    email_domain = True
                else:
                    email = False
            elif character in _ASCII_ALNUM:
                label_size += 1
                label_alnum = True
                email = label_size <= 63
            elif character == "-" and label_size:
                label_size += 1
                label_alnum = False
                email = label_size <= 63
            elif character == "." and label_size and label_alnum:
                label_size = 0
                label_alnum = False
            else:
                email = False
        if not uri and not email:
            return None
        at += 1
    viable_email = email and not (email_domain and label_size == 63 and not label_alnum)
    return len(text) if partial and (uri or viable_email) else None


def compact_angle_autolink_prefix(
    text: str, start: int, *, tokens: str = ""
) -> str | None:
    """Keep a bounded witness of a viable unfinished URI/email angle link."""
    if read_angle_autolink(text, start, partial=True) != len(text) or text.endswith(
        ">"
    ):
        return None
    body_start = start + 1
    colon = text.find(":", body_start, min(len(text), body_start + 33))
    if colon >= 0:
        # A viable colon cannot occur in an email address, so this is a URI body.
        return text[start : colon + 1] + "x" + tokens
    address = text.find("@", body_start)
    if address >= 0:
        label_start = text.rfind(".", address + 1) + 1
        label_start = max(label_start, address + 1)
        size = len(text) - label_start
        label = "x" * size
        if size and text.endswith("-"):
            label = label[:-1] + "-"
        return "<x" + tokens + "@" + ("x." if label_start > address + 1 else "") + label
    size = len(text) - body_start
    if not size:
        return "<" + tokens
    first = text[body_start]
    scheme_name = (
        first.isascii()
        and first.isalpha()
        and all(
            character.isascii() and (character.isalnum() or character in "+.-")
            for character in text[body_start:]
        )
    )
    if scheme_name:
        # Keep actual short names, including partial raw-HTML names. A long name
        # must stay longer than 32 characters so it cannot acquire a URI scheme.
        name = text[body_start:] if size <= 32 else "z" * 33
        return "<" + name + tokens
    # A period is plain Markdown text and email atext, but cannot become either
    # an HTML opener or a URI scheme. Existing literal delimiter state is supplied by tokens.
    return "<." + tokens


@dataclass(frozen=True)
class PhysicalLine:
    """One CRLF, LF or CR line in the original source."""

    start: int
    content_end: int
    end: int


def physical_lines(text: str) -> list[PhysicalLine]:
    """Index physical Markdown lines without normalizing marker text."""
    lines: list[PhysicalLine] = []
    start = 0
    for ending in COMPILED_PHYSICAL_LINE_END_REGEX.finditer(text):
        lines.append(PhysicalLine(start, ending.start(), ending.end()))
        start = ending.end()
    lines.append(PhysicalLine(start, len(text), len(text)))
    return lines


def column_at(line: str, offset: int, *, column: int = 0) -> int:
    """Count Markdown tab stops in the ASCII container prefix."""
    for character in line[:offset]:
        column += 4 - column % 4 if character == "\t" else 1
    return column


def indentation(
    line: str, start: int, virtual: int = 0, *, column: int | None = None
) -> tuple[int, int]:
    """Return the first content offset and remaining indentation columns."""
    column = column_at(line, start) if column is None else column
    first = column
    at = start
    while at < len(line) and line[at] in " \t":
        column += 4 - column % 4 if line[at] == "\t" else 1
        at += 1
    return at, virtual + column - first


def container_opening_info(
    line: str, *, column: int = 0, virtual: int = 0
) -> tuple[int, tuple[int, ...], int]:
    """Read explicit containers without consuming their following code indentation."""
    at = 0
    steps: list[int] = []
    # Index the eligible suffix once instead of rescanning it at every list level.
    thematic_start = thematic_limit = -1
    thematic_marker = ""
    thematic_size = 0
    for offset in range(len(line) - 1, -1, -1):
        character = line[offset]
        if character in " \t":
            continue
        if not thematic_marker and character in "*-_":
            thematic_marker = character
        if character != thematic_marker:
            break
        thematic_size += 1
        if thematic_size == 3:
            thematic_limit = offset
        if thematic_size >= 3:
            thematic_start = offset
    while at < len(line):
        before, before_column, before_virtual = at, column, virtual
        spaces = virtual
        virtual = 0
        while at < len(line) and line[at] in " \t":
            width = 4 - column % 4 if line[at] == "\t" else 1
            if spaces + width > 3:
                return before, tuple(steps), before_virtual
            at += 1
            column += width
            spaces += width
        if at < len(line) and line[at] == ">" and spaces <= 3:
            steps.append(0)
            at += 1
            column += 1
            if at < len(line) and line[at] in " \t":
                width = 4 - column % 4 if line[at] == "\t" else 1
                column += width
                virtual = width - 1
                at += 1
            continue
        if thematic_start >= 0 and thematic_start <= at <= thematic_limit:
            return before, tuple(steps), before_virtual
        marker = COMPILED_CONTAINER_LIST_REGEX.match(line, at)
        if marker is None or spaces > 3:
            return before, tuple(steps), before_virtual
        column += marker.end() - at
        at = marker.end()
        padding_start, padding_column = at, column
        while at < len(line) and line[at] in " \t":
            column += 4 - column % 4 if line[at] == "\t" else 1
            at += 1
        if at == len(line):
            required = padding_column - before_column + before_virtual + 1
        elif column - padding_column > 4:
            width = 4 - padding_column % 4 if line[padding_start] == "\t" else 1
            at = padding_start + 1
            column = padding_column + width
            virtual = width - 1
            required = padding_column - before_column + before_virtual + 1
        else:
            required = column - before_column + before_virtual
        steps.append(required)
    return at, tuple(steps), virtual


def container_opening(line: str) -> tuple[int, tuple[int, ...]]:
    """Return the original content offset and explicit container requirements."""
    at, steps, _ = container_opening_info(line)
    return at, steps


def container_content_info(
    line: str, steps: tuple[int, ...], *, partial: bool = False
) -> tuple[int, int] | None:
    """Retain tab overshoot after matching the opening containers."""
    at = column = virtual = 0
    for step in steps:
        if step == 0:
            spaces, virtual = virtual, 0
            while at < len(line) and line[at] in " \t":
                width = 4 - column % 4 if line[at] == "\t" else 1
                if spaces + width > 3:
                    return (
                        (len(line), 0)
                        if partial and not line[at:].strip(" \t")
                        else None
                    )
                at += 1
                column += width
                spaces += width
            if at >= len(line) or line[at] != ">" or spaces > 3:
                return (at, 0) if partial and at == len(line) else None
            at += 1
            column += 1
            if at < len(line) and line[at] in " \t":
                width = 4 - column % 4 if line[at] == "\t" else 1
                at += 1
                column += width
                virtual = width - 1
        else:
            consumed, virtual = virtual, 0
            while consumed < step:
                if at >= len(line):
                    return (at, 0) if partial else None
                if line[at] not in " \t":
                    return None
                width = 4 - column % 4 if line[at] == "\t" else 1
                consumed += width
                column += width
                at += 1
            virtual = consumed - step
    return at, virtual


def container_content_start(
    line: str, steps: tuple[int, ...], *, partial: bool = False
) -> int | None:
    """Locate a continuation while preserving source offsets."""
    content = container_content_info(line, steps, partial=partial)
    return content[0] if content is not None else None


def container_ancestor_info(
    line: str, steps: tuple[int, ...]
) -> tuple[int, int, tuple[int, ...]]:
    """Recover the longest matching ancestor after a full prefix failed."""
    matched, unmatched = 0, len(steps)
    info = (0, 0)
    while matched + 1 < unmatched:
        depth = (matched + unmatched) // 2
        candidate = container_content_info(line, steps[:depth])
        if candidate is None:
            unmatched = depth
        else:
            matched, info = depth, candidate
    return info[0], info[1], steps[:matched]


def fence_opening(
    line: str, *, column: int = 0, virtual: int = 0
) -> tuple[str, int, tuple[int, ...]] | None:
    """Recognize a fence after native container and indentation columns."""
    at, steps, virtual = container_opening_info(line, column=column, virtual=virtual)
    at, width = indentation(
        line, at, virtual, column=column_at(line, at, column=column)
    )
    if width > 3:
        return None
    fence = COMPILED_DOCUMENT_FENCE_REGEX.match(line, at)
    if fence is None:
        return None
    run = fence.group(1) or fence.group(3)
    return run[0], len(run), steps


@dataclass(frozen=True)
class BlockSpan:
    """An owned literal region and its local example boundaries."""

    end: int
    opening_end: int
    body_end: int
    marker: str = ""
    size: int = 0
    steps: tuple[int, ...] = ()
    closed: bool = False
    html_provisional: bool = False
    html_name_pending: bool = False


class DocumentBlocks:
    """Read the block boundaries needed by variable document scanners."""

    def __init__(self, text: str, html: Pattern[str]) -> None:
        """Index once using the caller's existing native HTML grammar."""
        self.text = text
        self.html_pattern = html
        self._html_token_ends: dict[tuple[int, bool], int | None] = {}
        self._container_ends: dict[tuple[int, tuple[int, ...], bool], int] = {}
        self._html_last_ends: dict[str, int] | None = None
        self._label_tab_widths: dict[int, int] | None = None
        self.lines = physical_lines(text)
        self.closed_fence_lines: set[int] = set()
        self.closed_html_lines: set[int] = set()
        self.closed_reference_lines: set[int] = set()
        self.closed_indented_lines: set[int] = set()
        self.closed_heading_lines: set[int] = set()
        self.unclosed_html_start: int | None = None
        self.content_starts = [line.start for line in self.lines]
        self.container_steps: list[tuple[int, ...]] = [() for _ in self.lines]
        self.paragraph_steps: list[tuple[int, ...]] = [() for _ in self.lines]
        self.virtual_padding = [0 for _ in self.lines]
        self.starts = [line.start for line in self.lines]
        self.by_start = {line.start: index for index, line in enumerate(self.lines)}
        self.container_paragraphs: set[int] = set()
        self.container_paragraphs = self._container_paragraphs()
        self._container_ends.clear()

    def line_at(self, offset: int) -> PhysicalLine:
        """Return the original physical line containing an offset."""
        return self.lines[max(0, bisect_right(self.starts, offset) - 1)]

    def blank(self, index: int) -> bool:
        """Test Markdown blank padding rather than all Unicode whitespace."""
        return not self.projected_line(index).strip(" \t")

    def label_character_size(self, at: int) -> int:
        """Count the browser tokenizer units at an original physical source offset."""
        character = self.text[at]
        if character in "\r\n":
            return 0
        if character != "\t":
            return 2 if ord(character) > 0xFFFF else 1
        if self._label_tab_widths is None:
            self._label_tab_widths = {}
            column = 0
            for offset, value in enumerate(self.text):
                if value in "\r\n":
                    column = 0
                elif value == "\t":
                    width = 4 - column % 4
                    self._label_tab_widths[offset] = width
                    column += width
                elif offset or value != "\ufeff":
                    column += 2 if ord(value) > 0xFFFF else 1
        return self._label_tab_widths[at]

    def projected_line(self, index: int) -> str:
        """Read native block context after its container prefix at original offsets."""
        line = self.lines[index]
        value = self.text[line.start : line.content_end]
        at, width = indentation(
            value, self.content_starts[index] - line.start, self.virtual_padding[index]
        )
        return " " * min(width, 4) + value[at:]

    def block_content_start(self, index: int) -> int | None:
        """Locate native block syntax after at most three indentation columns."""
        line = self.lines[index]
        at, width = indentation(
            self.text[line.start : line.content_end],
            self.content_starts[index] - line.start,
            self.virtual_padding[index],
        )
        return line.start + at if width < 4 else None

    def html_token_end(
        self, index: int, start: int, *, final: bool = True
    ) -> int | None:
        """Read a native HTML token without changing original variable text."""
        key = (start, final)
        if key in self._html_token_ends:
            return self._html_token_ends[key]
        limit = self.container_end(index, final=final)
        token = self.html_pattern.match(self.text, start, limit)
        steps = self.container_steps[index]
        project = token is None and bool(steps)
        if token is not None and steps:
            line = self.line_at(token.end() - 1)
            content = container_content_start(
                self.text[line.start : line.content_end],
                steps,
                partial=not final and line.end == line.content_end == len(self.text),
            )
            project = content is not None and token.end() - 1 < line.start + content
        end = token.end() if token is not None else None
        if project:
            base = self.lines[index].start
            pieces: list[str] = []
            for following in range(index, len(self.lines)):
                line = self.lines[following]
                if line.start >= limit:
                    break
                value = self.text[line.start : line.end]
                content = (
                    self.content_starts[following] - line.start
                    if following == index
                    else container_content_start(
                        value,
                        steps,
                        partial=not final
                        and line.end == line.content_end == len(self.text),
                    )
                )
                pieces.append(
                    " " * content + value[content:] if content is not None else value
                )
            native = "".join(pieces)
            token = self.html_pattern.match(native, start - base)
            end = base + token.end() if token is not None else None
        self._html_token_ends[key] = end
        return end

    def container_end(self, index: int, *, final: bool = True) -> int:
        """Bound a concrete native block before a confirmed container dedent."""
        steps = self.container_steps[index]
        if not steps:
            return len(self.text)
        key = (index, steps, final)
        if key in self._container_ends:
            return self._container_ends[key]
        covered = [index]
        end = len(self.text)
        for following in range(index + 1, len(self.lines)):
            line = self.lines[following]
            value = self.text[line.start : line.content_end]
            if container_content_start(value, steps) is None and value.strip(" \t"):
                partial = container_content_start(value, steps, partial=True)
                if not (
                    partial == len(value)
                    or (
                        not final
                        and line.end == line.content_end == len(self.text)
                        and partial is not None
                    )
                ):
                    end = line.start
                    break
            following_key = (following, steps, final)
            if following_key in self._container_ends:
                # The cached query excludes its own line, which was checked above.
                end = self._container_ends[following_key]
                break
            covered.append(following)
        for following in covered:
            self._container_ends[(following, steps, final)] = end
        return end

    def fence(self, start: int, *, final: bool = True) -> BlockSpan | None:
        """Read plain or quote/list-contained fenced code."""
        index = self.by_start.get(start)
        if index is None:
            return None
        first = self.lines[index]
        content = self.content_starts[index]
        opening = fence_opening(
            self.text[content : first.content_end],
            column=column_at(self.text[start : first.content_end], content - start),
            virtual=self.virtual_padding[index],
        )
        if opening is None or opening[2]:
            return None
        marker, size, nested = opening
        steps = self.container_steps[index] + nested
        previous = first
        for line in self.lines[index + 1 :]:
            value = self.text[line.start : line.content_end]
            content = container_content_start(value, steps)
            if content is None:
                if (
                    not final
                    and line.end == line.content_end == len(self.text)
                    and container_content_start(value, steps, partial=True) is not None
                ):
                    return BlockSpan(
                        len(self.text), first.end, len(self.text), marker, size, steps
                    )
                if not value.strip(" \t") or container_content_start(
                    value, steps, partial=True
                ) == len(value):
                    continue
                return BlockSpan(
                    previous.content_end,
                    first.end,
                    previous.content_end,
                    marker,
                    size,
                    steps,
                )
            info = container_content_info(value, steps)
            virtual = info[1] if info is not None else 0
            body_at, width = indentation(value, content, virtual)
            if width <= 3:
                run = value[body_at:].rstrip(" \t")
                if len(run) >= size and run == marker * len(run):
                    self.closed_fence_lines.add(line.start)
                    return BlockSpan(
                        line.content_end,
                        first.end,
                        line.start,
                        marker,
                        size,
                        steps,
                        closed=True,
                    )
            previous = line
        return BlockSpan(len(self.text), first.end, len(self.text), marker, size, steps)

    def terminated_html(self, start: int, *, final: bool = True) -> BlockSpan | None:
        """Keep complete native HTML blocks 2-5 through their closing physical line."""
        index = self.by_start.get(start)
        if index is None:
            return None
        at = self.block_content_start(index)
        if at is None:
            return None
        padding_end = at + 3
        while at < min(padding_end, len(self.text)) and self.text[at] == " ":
            at += 1
        special = self.text.startswith(("<!--", "<?", "<![CDATA["), at)
        declaration = (
            self.text.startswith("<!", at)
            and at + 2 < len(self.text)
            and self.text[at + 2].isascii()
            and self.text[at + 2].isalpha()
        )
        if not special and not declaration:
            return None
        if self.text.startswith("<!--", at):
            closing = ">" if self.text.startswith(("<!-->", "<!--->"), at) else "-->"
        elif self.text.startswith("<?", at):
            closing = "?>"
        elif self.text.startswith("<![CDATA[", at):
            closing = "]]>"
        else:
            closing = ">"
        if self._html_last_ends is None:
            self._html_last_ends = {
                ending: self.text.rfind(ending) for ending in (">", "-->", "?>", "]]>")
            }
        limit = self.container_end(index, final=final)
        token_end = (
            self.html_token_end(index, at, final=final)
            if self._html_last_ends[closing] >= at
            else None
        )
        if token_end is None:
            # A confirmed parent-container dedent ends native HTML even without a terminator.
            # Plain EOF retains the historical incomplete-token fallback.
            if self.container_steps[index] and limit < len(self.text):
                return BlockSpan(limit, at, limit, closed=True)
            if self.unclosed_html_start is None and (
                special or "A" <= self.text[at + 2] <= "Z"
            ):
                self.unclosed_html_start = start
            return None
        end = self.line_at(token_end).content_end
        return BlockSpan(end, token_end, end, closed=True)

    def raw_html(self, start: int) -> BlockSpan | None:
        """Keep raw-text HTML paragraph state through its closing physical line."""
        index = self.by_start.get(start)
        if index is None:
            return None
        content = self.block_content_start(index)
        if content is None or self.text.startswith("</", content):
            return None
        tag = COMPILED_DOCUMENT_TAG_REGEX.match(
            self.text, content, self.lines[index].content_end
        )
        if tag is None or tag.group(1).lower() not in (
            "script",
            "style",
            "pre",
            "textarea",
        ):
            return None
        if self.text[tag.end() : tag.end() + 1] not in (
            " ",
            "\t",
            "\r",
            "\n",
            "\f",
            ">",
        ):
            return None
        opening_end = self.html_token_end(index, content) or tag.end()
        limit = self.container_end(index)
        closing = re.compile(
            r"</" + tag.group(1) + r"[ \t\r\n]*>", re.IGNORECASE
        ).search(self.text, opening_end, limit)
        end = self.line_at(closing.end()).content_end if closing is not None else limit
        if closing is None and limit < len(self.text):
            self.closed_html_lines.add(self.line_at(max(start, limit - 1)).start)
        return BlockSpan(end, opening_end, end, closed=closing is not None)

    def ordinary_html(
        self, start: int, *, final: bool = True, project_blank: bool = True
    ) -> BlockSpan | None:
        """Bound native type-six/seven HTML blocks at the first blank line."""
        index = self.by_start.get(start)
        if index is None:
            return None
        first = self.lines[index]
        content_start = self.block_content_start(index)
        if content_start is None:
            return None
        opening = COMPILED_DOCUMENT_TAG_REGEX.match(
            self.text[content_start : first.content_end]
        )
        if opening is None:
            return None
        tag_start = self.text.find("<", content_start, first.content_end)
        block_tag = opening.group(1).lower() in HTML_BLOCK_TAGS
        if not block_tag and index and not self.indented_may_start(index):
            return None
        token = self.html_token_end(index, tag_start, final=final)
        token_end = token if token is not None else start
        if not block_tag and (
            token is None
            or token_end > first.content_end
            or self.text[token_end : first.content_end].strip(" \t")
        ):
            return None
        previous = self.line_at(token_end)
        scan = max(index + 1, self.by_start.get(previous.start, index))
        for at in range(scan, len(self.lines)):
            line = self.lines[at]
            steps = self.container_steps[index]
            value = self.text[line.start : line.content_end]
            content = container_content_start(value, steps)
            partial = (
                not final
                and line.end == line.content_end == len(self.text)
                and container_content_start(value, steps, partial=True) is not None
            )
            outside = (
                bool(steps)
                and bool(value.strip(" \t"))
                and not partial
                and content is None
            )
            # Future container prefixes are not indexed during the constructor pass.
            blank = (
                self.blank(at)
                if project_blank
                else not value[content if content is not None else 0 :].strip(" \t")
            )
            if line.start >= token_end and (blank or outside):
                if outside:
                    self.closed_html_lines.add(previous.start)
                return BlockSpan(
                    previous.content_end,
                    token_end,
                    previous.content_end,
                    closed=bool(outside) or line.end > line.content_end,
                )
            previous = line
        return BlockSpan(
            len(self.text),
            token_end,
            len(self.text),
            html_provisional=(
                not final and not block_tag and first.end == first.content_end
            ),
            html_name_pending=(
                not final
                and block_tag
                and content_start + opening.end() == len(self.text)
            ),
        )

    def indented_may_start(self, index: int) -> bool:
        """Allow code after a blank or a confirmed non-paragraph block."""
        if index == 0 or self.blank(index - 1):
            return True
        previous = self.lines[index - 1]
        value = self.projected_line(index - 1)
        return bool(
            previous.start in self.closed_fence_lines
            or previous.start in self.closed_html_lines
            or previous.start in self.closed_reference_lines
            or previous.start in self.closed_indented_lines
            or previous.start in self.closed_heading_lines
            or COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(value) is not None
            or (value.startswith("__MDFLOW_CODE_BLOCK_") and value.endswith("__"))
        )

    def reference_prefix(self, start: int) -> int | None:
        """Read a bounded reference definition prefix at original source offsets."""
        prefix = self.reference_label_prefix(start)
        return prefix[0] if prefix is not None else None

    def reference_label_prefix(self, start: int) -> tuple[int, str] | None:
        """Read the label and resource offset across native continuation lines."""
        index = self.by_start.get(start)
        if index is None:
            return None
        line = self.lines[index]
        if not self.indented_may_start(index) and not self.paragraph_interrupts(index):
            return None
        content_start = self.block_content_start(index)
        if (
            content_start is None
            and index
            and self.lines[index - 1].start in self.closed_reference_lines
            and not self.paragraph_interrupts(index)
            and self.paragraph_steps[index] == self.paragraph_steps[index - 1]
        ):
            # Consecutive definitions share a content block, whose continuation
            # indentation is consumed before a new indented-code block can start.
            content, _ = indentation(
                self.text[line.start : line.content_end],
                self.content_starts[index] - line.start,
                self.virtual_padding[index],
            )
            content_start = line.start + content
        if content_start is None:
            return None
        match = COMPILED_REFERENCE_PREFIX_REGEX.match(
            self.text[content_start : line.content_end]
        )
        if match is not None:
            label = match.group(1)
            label_start = content_start + match.start(1)
            if (
                len(label) <= 999
                and sum(
                    self.label_character_size(at)
                    for at in range(label_start, label_start + len(label))
                )
                <= 999
                and label.strip(" \t")
            ):
                return content_start + match.end(), label
            return None
        if self.text[content_start : content_start + 1] != "[":
            return None
        at = content_start + 1
        label_parts: list[str] = []
        size = 0
        steps = self.container_steps[index]
        while at < len(self.text) and size <= 999:
            character = self.text[at]
            if character == "]":
                label = "".join(label_parts)
                if self.text[at + 1 : at + 2] != ":" or not label.strip():
                    return None
                at += 2
                while at < len(self.text) and self.text[at] in " \t":
                    at += 1
                return at, label
            if character == "[":
                return None
            if character == "\\" and at + 1 < len(self.text):
                label_parts.append(character)
                size += 1
                at += 1
                character = self.text[at]
                if character not in "\r\n":
                    label_parts.append(character)
                    size += self.label_character_size(at)
                    at += 1
                    continue
            if character in "\r\n":
                index += 1
                if index >= len(self.lines):
                    return None
                line = self.lines[index]
                content, value, _, virtual = self.reference_projection(index, steps)
                if not value.strip(" \t"):
                    return None
                if self.reference_block_interrupts(value):
                    return None
                size += virtual
                at = content
                while at < line.content_end and self.text[at] in " \t":
                    size += self.label_character_size(at)
                    at += 1
                label_parts.append("\n")
                continue
            label_parts.append(character)
            size += self.label_character_size(at)
            at += 1
        return None

    def reference_projection(
        self, index: int, steps: tuple[int, ...]
    ) -> tuple[int, str, bool, int]:
        """Project reference lookahead independently of future paragraph indexing."""
        line = self.lines[index]
        value = self.text[line.start : line.content_end]
        info = container_content_info(value, steps)
        if info is None:
            content, virtual, _ = container_ancestor_info(value, steps)
        else:
            content, virtual = info
        remaining = value[content:]
        _, opening, _ = container_opening_info(
            remaining, column=column_at(value, content), virtual=virtual
        )
        interrupt = bool(opening)
        at, width = indentation(value, content, virtual)
        return (
            line.start + content,
            " " * min(width, 4) + value[at:],
            interrupt,
            virtual,
        )

    def reference_space(self, start: int, origin: int) -> int | None:
        """Skip reference padding through matching container continuation prefixes."""
        steps = self.container_steps[self.by_start[self.line_at(origin).start]]
        at = start
        while at < len(self.text):
            index = self.by_start.get(at)
            if index is not None and at > origin:
                content, value, interrupt, _ = self.reference_projection(index, steps)
                if not value.strip(" \t"):
                    return None
                if interrupt or self.reference_block_interrupts(value):
                    return None
                at = content
            if at >= len(self.text) or self.text[at] not in " \t\r\n":
                break
            at += 1
        return at

    def reference_has_blank(
        self, start: int, end: int, *, origin: int | None = None
    ) -> bool:
        """Test only whole intervening physical lines after container projection."""
        first = self.by_start[self.line_at(start).start]
        last = self.by_start[self.line_at(end).start]
        origin_line = self.line_at(start if origin is None else origin)
        steps = self.container_steps[self.by_start[origin_line.start]]
        return any(
            not self.reference_projection(index, steps)[1].strip(" \t")
            for index in range(first + 1, last)
        )

    @staticmethod
    def reference_block_interrupts(value: str) -> bool:
        """Recognize native non-container interruptions during reference lookahead."""
        tag = COMPILED_DOCUMENT_TAG_REGEX.match(value)
        return (
            COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(value) is not None
            or COMPILED_SETEXT_REGEX.fullmatch(value) is not None
            or COMPILED_REFERENCE_HTML_BREAK_REGEX.match(value) is not None
            or (
                tag is not None
                and tag.group(1).lower()
                in HTML_BLOCK_TAGS | {"script", "style", "pre", "textarea"}
            )
            or fence_opening(value) is not None
            or COMPILED_ATX_START_REGEX.match(value) is not None
        )

    def interaction_limit(
        self, start: int, marker_end: Callable[[int], int | None], *, final: bool = True
    ) -> tuple[int, bool]:
        """Stop incomplete document controls at a blank outside opaque markers."""
        at = start
        while at < len(self.text):
            index = self.by_start.get(at)
            if (
                index is not None
                and at > start
                and (final or self.lines[index].end > self.lines[index].content_end)
            ):
                value = self.projected_line(index)
                if (
                    self.blank(index)
                    or fence_opening(value) is not None
                    or COMPILED_ATX_START_REGEX.match(value) is not None
                    or self.inline_block_interrupts(index)
                    or self.paragraph_interrupts(index)
                ):
                    return at, False
            if self.text.startswith("{{", at):
                end = marker_end(at)
                if end is None:
                    return len(self.text), False
                at = end
            elif (
                self.text[at] == "\\"
                and at + 1 < len(self.text)
                and self.text[at + 1] in "|/.]"
            ):
                at += 2
            elif self.text[at] == "]":
                return at, True
            else:
                at += 1
        return len(self.text), False

    def _container_paragraphs(self) -> set[int]:
        """Keep same-container and lazy continuation lines in one paragraph."""
        boundaries = self.container_paragraphs
        active: tuple[int, ...] = ()
        paragraph = False
        empty_list_base: tuple[int, ...] | None = None
        literal_end = 0
        literal_steps: tuple[int, ...] = ()
        literal_paragraph = False
        # The component's no-title definition probe stays concrete until another
        # nonblank line resolves it; new quote/list containers cannot pierce it.
        pending_reference: Literal["definition", "destination"] | None = None
        pending_indented: int | None = None
        for index, line in enumerate(self.lines):
            value = self.text[line.start : line.content_end]
            if line.start < literal_end:
                info = container_content_info(value, literal_steps, partial=True)
                content, virtual = info if info is not None else (0, 0)
                self.content_starts[index] = line.start + content
                self.virtual_padding[index] = virtual
                self.container_steps[index] = literal_steps if info is not None else ()
                if literal_paragraph:
                    self.paragraph_steps[index] = literal_steps
                active = literal_steps
                paragraph = literal_paragraph
                continue
            if not value.strip(" \t"):
                if empty_list_base is not None:
                    active = empty_list_base
                    empty_list_base = None
                paragraph = False
                continue
            info = container_content_info(value, active) if active else (0, 0)
            if info is None and active:
                blank_info = container_content_info(value, active, partial=True)
                if blank_info is not None and blank_info[0] == len(value):
                    self.content_starts[index] = line.content_end
                    self.container_steps[index] = active
                    self.virtual_padding[index] = blank_info[1]
                    if empty_list_base is not None:
                        active = empty_list_base
                        empty_list_base = None
                    paragraph = False
                    continue
            empty_list_base = None
            definition_continuation = pending_reference
            pending_reference = None
            indented_continuation = pending_indented
            pending_indented = None
            base = active if info is not None else ()
            exited = False
            if info is None:
                # A sibling item can start at any matched ancestor. Plain text
                # instead continues lazily without restarting that paragraph.
                offset, padding, base = container_ancestor_info(value, active)
                info = offset, padding
                exited = base != active
                if exited:
                    definition_continuation = None
                    indented_continuation = None
                if not paragraph:
                    active = base
            content, virtual = info if info is not None else (0, 0)
            remaining = value[content:]
            continuing_paragraph = paragraph
            if indented_continuation is not None:
                self.closed_indented_lines.add(indented_continuation)
            after, steps, opening_virtual = container_opening_info(
                remaining, column=column_at(value, content), virtual=virtual
            )
            entered = (
                bool(steps)
                and not definition_continuation
                and (
                    (not paragraph and indented_continuation is None)
                    or exited
                    or self._explicit_interrupt(remaining)
                )
            )
            if entered:
                boundaries.add(index)
                active = base + steps
                remaining = remaining[after:]
            self.content_starts[index] = (
                line.start + content + (after if entered else 0)
            )
            self.virtual_padding[index] = opening_virtual if entered else virtual
            # Bounds belong to physical prefixes, including lazy outer quotes.
            self.container_steps[index] = active if entered else base
            self.paragraph_steps[index] = active
            if not remaining.strip(" \t"):
                boundaries.add(index)
                paragraph = False
                pending_reference = definition_continuation
                pending_indented = indented_continuation
                if entered and active[-1] > 0:
                    empty_list_base = active[:-1]
            else:
                paragraph = True
            projected = self.projected_line(index)
            heading = COMPILED_ATX_START_REGEX.match(projected) is not None
            paragraph_fence = fence_opening(remaining)
            if (
                (paragraph_fence is not None and not paragraph_fence[2])
                or heading
                or COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(remaining) is not None
            ):
                paragraph = False
                active = self.container_steps[index]
            setext = (
                continuing_paragraph
                and not exited
                and not entered
                and self.lines[index - 1].start not in self.closed_reference_lines
                and COMPILED_SETEXT_REGEX.fullmatch(projected) is not None
            )
            if heading or setext:
                self.closed_heading_lines.add(line.start)
            if setext and definition_continuation == "destination":
                pending_reference = "destination"
            indented = (not continuing_paragraph or entered) and indentation(
                value,
                self.content_starts[index] - line.start,
                self.virtual_padding[index],
            )[1] >= 4
            if setext or indented:
                paragraph = False
                active = self.container_steps[index]
            if indented:
                pending_indented = line.start
            literal = (
                self.fence(line.start)
                or self.raw_html(line.start)
                or self.terminated_html(line.start)
                or self.ordinary_html(line.start, project_blank=False)
            )
            if literal is not None:
                literal_end = literal.end
                literal_paragraph = False
                if definition_continuation == "destination" and not literal.marker:
                    pending_reference = "destination"
                literal_steps = self.container_steps[index]
                paragraph = False
                active = literal_steps
                continue
            reference = self.reference_label_prefix(line.start)
            if reference is not None:
                resource = _read_reference_resource(
                    self.text, reference[0], self, origin=line.start
                )
                if resource is not None:
                    self.closed_reference_lines.add(self.line_at(resource.end).start)
                    literal_end = resource.end
                    literal_paragraph = True
                    pending_reference = (
                        "definition"
                        if (
                            not resource.titled
                            and (not continuing_paragraph or entered)
                            and not definition_continuation
                        )
                        else None
                    )
                    literal_steps = self.paragraph_steps[index]
                    paragraph = True
                    active = literal_steps
                elif reference[0] >= line.content_end:
                    pending_reference = "destination"
        return boundaries

    @staticmethod
    def _explicit_interrupt(value: str) -> bool:
        at = 0
        while at < min(3, len(value)) and value[at] == " ":
            at += 1
        if at < len(value) and value[at] == ">":
            return True
        marker = COMPILED_CONTAINER_LIST_REGEX.match(value, at)
        if marker is None or (
            value[at].isdigit() and marker.group() not in ("1.", "1)")
        ):
            return False
        return bool(value[marker.end() :].strip(" \t"))

    def paragraph_interrupts(self, index: int) -> bool:
        """Report a new quote/list paragraph without breaking its own inline spans."""
        return index in self.container_paragraphs

    def inline_block_interrupts(self, index: int) -> bool:
        """Report confirmed thematic and ordinary-HTML paragraph interruptions."""
        value = self.projected_line(index)
        tag = COMPILED_DOCUMENT_TAG_REGEX.match(value)
        return (
            COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(value) is not None
            or COMPILED_SETEXT_REGEX.fullmatch(value) is not None
            or (tag is not None and tag.group(1).lower() in HTML_BLOCK_TAGS)
        )


@dataclass(frozen=True)
class _ReferenceResource:
    """Validated definition syntax and its completed-title lookahead state."""

    end: int
    titled: bool = False


def read_reference_resource_end(
    text: str, start: int, blocks: DocumentBlocks, *, origin: int | None = None
) -> int | None:
    """Read definition syntax before a renderer applies its URL cleanup policy."""
    resource = _read_reference_resource(text, start, blocks, origin=origin)
    return resource.end if resource is not None else None


def _read_reference_resource(
    text: str, start: int, blocks: DocumentBlocks, *, origin: int | None = None
) -> _ReferenceResource | None:
    """Retain whether a completed title resolved the definition lookahead."""
    origin = start if origin is None else origin
    at = blocks.reference_space(start, origin)
    if at is None or at >= len(text):
        return None
    destination_start = at
    if text[at] == "<":
        at += 1
        while at < len(text):
            if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
            elif text[at] == ">":
                at += 1
                break
            elif text[at] in "<\r\n":
                return None
            else:
                at += 1
        else:
            return None
    else:
        depth = 0
        while at < len(text) and text[at] not in " \t\r\n":
            character = text[at]
            if character == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
                at += 2
                continue
            if character == "(":
                depth += 1
                if depth > 32:
                    return None
            elif character == ")":
                depth -= 1
                if depth < 0:
                    return None
            elif ord(character) < 32 or character == "\x7f":
                return None
            at += 1
        if depth:
            return None
    if at == destination_start:
        return None
    destination_end = at
    destination_line = blocks.line_at(destination_end)
    fallback = (
        _ReferenceResource(destination_line.content_end)
        if not text[destination_end : destination_line.content_end].strip(" \t")
        else None
    )
    at = blocks.reference_space(at, origin)
    if at is None or at >= len(text) or text[at] not in "\"'(":
        return fallback
    title_next_line = at > destination_line.content_end
    if at == destination_end:
        return None
    closing = ")" if text[at] == "(" else text[at]
    at += 1
    title_start = at
    while at < len(text):
        index = blocks.by_start.get(at)
        if index is not None:
            steps = blocks.container_steps[
                blocks.by_start[blocks.line_at(origin).start]
            ]
            content, value, _, _ = blocks.reference_projection(index, steps)
            if not value.strip(" \t") or blocks.reference_block_interrupts(value):
                return fallback if title_next_line else None
            at = content
        if text[at] == "\\" and at + 1 < len(text) and text[at + 1] in punctuation:
            at += 2
        elif text[at] == closing:
            line_end = blocks.line_at(at).content_end
            if blocks.reference_has_blank(title_start, at, origin=origin) or text[
                at + 1 : line_end
            ].strip(" \t"):
                return fallback if title_next_line else None
            return _ReferenceResource(line_end, titled=True)
        else:
            at += 1
    return fallback if title_next_line else None
