"""Physical Markdown block boundaries with original source offsets."""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern

COMPILED_PHYSICAL_LINE_END_REGEX = re.compile(r"\r\n|\r|\n")
COMPILED_CONTAINER_LIST_REGEX = re.compile(r"(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t])")
COMPILED_DOCUMENT_FENCE_REGEX = re.compile(r"(`{3,})([^`]*$)|(~{3,})(.*$)")
COMPILED_DOCUMENT_TAG_REGEX = re.compile(
    r" {0,3}</?([A-Za-z][A-Za-z0-9-]*)(?=[ \t/>]|$)"
)


COMPILED_REFERENCE_PREFIX_REGEX = re.compile(
    r" {0,3}\[((?:\\[^\r\n]|[^\]\\\r\n])+)]\:[ \t]*"
)
COMPILED_ATX_START_REGEX = re.compile(r" {0,3}#{1,6}(?=[ \t]|$)")
COMPILED_DOCUMENT_BREAK_REGEX = re.compile(
    r" {0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"
)
COMPILED_SETEXT_REGEX = re.compile(r" {0,3}(?:=+|-+)[ \t]*$")

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
                # source offsets and raw question text remain untouched.
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
        marker = COMPILED_CONTAINER_LIST_REGEX.match(line, at)
        if marker is None or spaces > 3:
            return before, tuple(steps), before_virtual
        column += marker.end() - at
        at = marker.end()
        padding_start, padding_column = at, column
        while at < len(line) and line[at] in " \t":
            column += 4 - column % 4 if line[at] == "\t" else 1
            at += 1
        if column - padding_column > 4:
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
    """Read the block boundaries needed by question document scanners."""

    def __init__(self, text: str, html: Pattern[str]) -> None:
        """Index once using the caller's existing native HTML grammar."""
        self.text = text
        self.html_pattern = html
        self._html_token_ends: dict[tuple[int, bool], int | None] = {}
        self._container_ends: dict[tuple[int, bool], int] = {}
        self._html_last_ends: dict[str, int] | None = None
        self.lines = physical_lines(text)
        self.closed_fence_lines: set[int] = set()
        self.closed_html_lines: set[int] = set()
        self.content_starts = [line.start for line in self.lines]
        self.container_steps: list[tuple[int, ...]] = [() for _ in self.lines]
        self.virtual_padding = [0 for _ in self.lines]
        self.container_paragraphs = self._container_paragraphs()
        self.starts = [line.start for line in self.lines]
        self.by_start = {line.start: index for index, line in enumerate(self.lines)}

    def line_at(self, offset: int) -> PhysicalLine:
        """Return the original physical line containing an offset."""
        return self.lines[max(0, bisect_right(self.starts, offset) - 1)]

    def blank(self, index: int) -> bool:
        """Test Markdown blank padding rather than all Unicode whitespace."""
        return not self.projected_line(index).strip(" \t")

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
        """Read a native HTML token without changing original question text."""
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
        key = (index, final)
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
            if self.container_steps[following] == steps:
                following_key = (following, final)
                if following_key in self._container_ends:
                    # The cached query excludes its own line, which was checked above.
                    end = self._container_ends[following_key]
                    break
                covered.append(following)
        for following in covered:
            self._container_ends[(following, final)] = end
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
        if opening is None:
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
            return None
        end = self.line_at(token_end).content_end
        return BlockSpan(end, token_end, end, closed=True)

    def ordinary_html(self, start: int, *, final: bool = True) -> BlockSpan | None:
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
        if not block_tag and index and not self.blank(index - 1):
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
            partial = (
                not final
                and line.end == line.content_end == len(self.text)
                and container_content_start(value, steps, partial=True) is not None
            )
            outside = (
                bool(steps)
                and bool(value.strip(" \t"))
                and not partial
                and container_content_start(value, steps) is None
            )
            if line.start >= token_end and (self.blank(at) or outside):
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
            or COMPILED_ATX_START_REGEX.match(value) is not None
            or COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(value) is not None
            or (
                index > 1
                and not self.blank(index - 2)
                and COMPILED_SETEXT_REGEX.fullmatch(value) is not None
            )
            or (value.startswith("__MDFLOW_CODE_BLOCK_") and value.endswith("__"))
        )

    def reference_prefix(self, start: int) -> int | None:
        """Read the bounded single-line label prefix of a reference definition."""
        index = self.by_start.get(start)
        if index is None:
            return None
        line = self.lines[index]
        if (
            self.container_steps[index]
            and not self.indented_may_start(index)
            and not self.paragraph_interrupts(index)
        ):
            return None
        content_start = self.block_content_start(index)
        if content_start is None:
            return None
        match = COMPILED_REFERENCE_PREFIX_REGEX.match(
            self.text[content_start : line.content_end]
        )
        if (
            match is None
            or len(match.group(1)) > 999
            or not match.group(1).strip(" \t")
        ):
            return None
        return content_start + match.end()

    def reference_space(self, start: int, origin: int) -> int | None:
        """Skip reference padding through matching container continuation prefixes."""
        steps = self.container_steps[self.by_start[self.line_at(origin).start]]
        at = start
        while at < len(self.text):
            index = self.by_start.get(at)
            if index is not None and at > origin:
                line = self.lines[index]
                content = container_content_start(
                    self.text[at : line.content_end], steps
                )
                if self.blank(index):
                    return None
                if content is None:
                    value = self.projected_line(index)
                    if (
                        self.paragraph_interrupts(index)
                        or self.inline_block_interrupts(index)
                        or fence_opening(value) is not None
                        or COMPILED_ATX_START_REGEX.match(value) is not None
                    ):
                        return None
                    content = 0  # A definition permits a lazy paragraph continuation.
                at += content
            if at >= len(self.text) or self.text[at] not in " \t\r\n":
                break
            at += 1
        return at

    def reference_has_blank(self, start: int, end: int) -> bool:
        """Test only whole intervening physical lines after container projection."""
        first = self.by_start[self.line_at(start).start]
        last = self.by_start[self.line_at(end).start]
        return any(self.blank(index) for index in range(first + 1, last))

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
        boundaries: set[int] = set()
        active: tuple[int, ...] = ()
        paragraph = False
        for index, line in enumerate(self.lines):
            value = self.text[line.start : line.content_end]
            if not value.strip(" \t"):
                paragraph = False
                continue
            info = container_content_info(value, active) if active else (0, 0)
            if info is None and active:
                blank_info = container_content_info(value, active, partial=True)
                if blank_info is not None and blank_info[0] == len(value):
                    self.content_starts[index] = line.content_end
                    self.container_steps[index] = active
                    self.virtual_padding[index] = blank_info[1]
                    paragraph = False
                    continue
            if info is None and not paragraph:
                active = ()
            content, virtual = info if info is not None else (0, 0)
            remaining = value[content:]
            base = active if info is not None else ()
            after, steps, opening_virtual = container_opening_info(
                remaining, column=column_at(value, content), virtual=virtual
            )
            entered = bool(steps) and (
                not paragraph or self._explicit_interrupt(remaining)
            )
            if entered:
                boundaries.add(index)
                active = base + steps
                remaining = remaining[after:]
            self.content_starts[index] = (
                line.start + content + (after if entered else 0)
            )
            self.virtual_padding[index] = opening_virtual if entered else virtual
            self.container_steps[index] = active if info is not None or entered else ()
            if not remaining.strip(" \t"):
                boundaries.add(index)
                paragraph = False
            else:
                paragraph = True
            if (
                fence_opening(remaining) is not None
                or COMPILED_ATX_START_REGEX.match(remaining) is not None
                or COMPILED_DOCUMENT_BREAK_REGEX.fullmatch(remaining) is not None
            ):
                paragraph = False
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
