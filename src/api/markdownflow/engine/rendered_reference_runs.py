"""Reference ownership in the pinned ContentRender Markdown runs.

The UI parses ordinary backtick/SVG fragments separately. Native HTML keeps its
whole neighboring Markdown run; sandbox HTML separates reference inventories.
Source ranges come from the document scanner, preserving its marker grammar.
"""

import re
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

SANDBOX_ROOTS = frozenset(
    [
        "div",
        "style",
        "script",
        "iframe",
        "section",
        "article",
        "header",
        "footer",
        "nav",
        "main",
        "aside",
        "figure",
        "details",
        "summary",
        "form",
        "table",
        "canvas",
        "video",
        "audio",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "dl",
        "fieldset",
        "address",
        "hgroup",
        "center",
        "link",
        "html",
        "head",
        "body",
        "meta",
        "title",
        "base",
        "template",
    ]
)
NATIVE_ROOTS = frozenset(
    ["pre", "details", "summary", "aside", "blockquote", "ul", "ol", "dl", "table"]
)
WIDGET_ROOTS = frozenset(
    [
        "script",
        "style",
        "link",
        "iframe",
        "html",
        "head",
        "body",
        "meta",
        "title",
        "base",
        "template",
    ]
)
RAW_TEXT = frozenset(
    ["script", "style", "textarea", "title", "iframe", "xmp", "noembed", "noframes"]
)
VOID_TAGS = frozenset(
    [
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
    ]
)
NAME = re.compile(r"[a-z][a-z0-9:-]*", re.IGNORECASE)
ATTR = re.compile(r"""([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]*)))?""")
DOCTYPE = re.compile(r"<!doctype(?=[\s>])", re.IGNORECASE)
_NORMALIZED_LINE_END = re.compile(r"\r?\n")
_HTML_LINE = re.compile(r"<[/!a-zA-Z]")
_TRIM_SPACE = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"


@dataclass(frozen=True)
class RenderProjection:
    """Normalized Markdown with a monotonic map back to original source offsets."""

    text: str
    starts: tuple[int, ...]
    origins: tuple[int, ...]

    def raw_offset(self, at: int) -> int:
        """Map a normalized character or span end to its original source offset."""
        index = bisect_right(self.starts, at) - 1
        return self.origins[index] + at - self.starts[index]


def normalize_markdown_run(
    text: str, code_ranges: Iterable[tuple[int, int]]
) -> RenderProjection:
    """Apply the pinned UI's HTML indentation and CRLF normalization."""
    ranges = tuple(sorted(code_ranges))
    chunks: list[str] = []
    starts: list[int] = []
    origins: list[int] = []
    offset = rendered = code_index = 0
    in_fence = False
    endings = [
        (match.start(), match.end()) for match in _NORMALIZED_LINE_END.finditer(text)
    ]
    endings.append((len(text), len(text)))
    for end, following in endings:
        line = text[offset:end]
        trimmed = line.lstrip(_TRIM_SPACE)
        content = offset + len(line) - len(trimmed)
        while code_index < len(ranges) and ranges[code_index][1] <= content:
            code_index += 1
        code = ranges[code_index] if code_index < len(ranges) else None
        protected = (
            code is not None
            and code[0] <= content
            and text[code[0] : code[0] + 1] in {"`", "~"}
        )
        origin = offset
        if not protected:
            if trimmed.startswith("```"):
                in_fence = not in_fence
            elif not in_fence and _HTML_LINE.match(trimmed) is not None:
                line = trimmed
                origin = content
        starts.append(rendered)
        origins.append(origin)
        chunks.append(line)
        rendered += len(line)
        if following > end:
            chunks.append("\n")
            rendered += 1
        offset = following
    return RenderProjection("".join(chunks), tuple(starts), tuple(origins))


@dataclass(frozen=True)
class Markup:
    """A lexical tag boundary before rendering decides its owner."""

    kind: str
    end: int
    name: str = ""
    closing: bool = False
    self_closing: bool = False


@dataclass(frozen=True)
class Run:
    """A source interval parsed together by one UI renderer."""

    start: int
    end: int
    kind: str


class RunIndex:
    """Answer source ownership without rescanning preceding segments."""

    def __init__(self, runs: Iterable[Run]) -> None:
        """Index ordered, disjoint renderer runs once."""
        self.runs = tuple(runs)
        self.starts = tuple(run.start for run in self.runs)

    def owner(self, at: int) -> int:
        """Return the owning run index, or -1 outside the source intervals."""
        index = bisect_right(self.starts, at) - 1
        return index if index >= 0 and at < self.runs[index].end else -1


class FragmentIndex:
    """Index the literal tokens of mermaid-parse's lazy alternation once."""

    def __init__(self, text: str) -> None:
        """Index literal delimiters in a single source pass."""
        self.triples = []
        self.svgs = []
        self.closes = []
        for match in re.finditer(r"(?=(```|<svg|</svg>))", text):
            target = (
                self.triples
                if match.group(1) == "```"
                else self.svgs
                if match.group(1) == "<svg"
                else self.closes
            )
            target.append(match.start())

    def next(self, cursor: int, end: int) -> tuple[int, int, bool] | None:
        """Find the next complete backtick or SVG fragment from the cursor."""
        choices = []
        index = bisect_left(self.triples, cursor)
        if index < len(self.triples):
            closing = bisect_left(self.triples, self.triples[index] + 3)
            if closing < len(self.triples) and self.triples[closing] + 3 <= end:
                choices.append((self.triples[index], self.triples[closing] + 3, True))
        index = bisect_left(self.svgs, cursor)
        if index < len(self.svgs):
            close = bisect_left(self.closes, self.svgs[index] + 4)
            if close < len(self.closes) and self.closes[close] + 6 <= end:
                choices.append((self.svgs[index], self.closes[close] + 6, False))
        return min(choices) if choices else None


def markup(text: str, start: int) -> Markup:
    """Read a streaming HTML token without interpreting its contents."""
    if text.startswith("<!--", start):
        end = text.find("-->", start + 4)
        return (
            Markup("comment", end + 3) if end >= 0 else Markup("incomplete", len(text))
        )
    if start + 1 >= len(text):
        return Markup("incomplete", len(text))
    declaration = text[start + 1] in "!?"
    closing = text[start + 1] == "/"
    name_start = start + (2 if closing else 1)
    found = None if declaration else NAME.match(text, name_start)
    if not declaration and found is None:
        return Markup("incomplete" if name_start == len(text) else "invalid", start + 1)
    after = start + 2 if declaration else found.end()
    if after == len(text):
        return Markup("incomplete", len(text))
    if not declaration and not (text[after].isspace() or text[after] in "/>"):
        return Markup("invalid", start + 1)
    quote = ""
    for at in range(after, len(text)):
        character = text[at]
        if quote:
            if character == quote:
                quote = ""
        elif character in "\"'":
            quote = character
        elif character == ">":
            if declaration:
                return Markup("declaration", at + 1)
            return Markup(
                "tag",
                at + 1,
                found.group().lower(),
                closing,
                re.search(r"/\s*>$", text[start : at + 1]) is not None,
            )
    return Markup("incomplete", len(text))


def video_end(text: str, start: int) -> int | None:
    """Locate a complete or pending native video iframe."""
    token = markup(text, start)
    if token.kind != "tag" or token.name != "iframe" or token.closing:
        return None
    attributes = text[start + len("<iframe") : token.end - 1]
    for match in ATTR.finditer(attributes):
        if match.group(1).lower() == "data-tag":
            if (
                next(
                    (part for part in match.groups()[1:] if part is not None), ""
                ).lower()
                != "video"
            ):
                return None
            end = re.compile(r"</iframe\s*>", re.IGNORECASE).search(text, token.end)
            return end.end() if end is not None else len(text)
    return None


class _ClosingIndex:
    """Index structural closing tokens without treating raw-text strings as tags."""

    def __init__(self, text: str) -> None:
        self.positions: dict[str, list[int]] = {}
        for match in re.finditer(
            r"</([a-z][a-z0-9:-]*)(?=[\s/>])", text, re.IGNORECASE
        ):
            self.positions.setdefault(match.group(1).lower(), []).append(match.start())
        self.trees = {
            name: [0] * (len(starts) + 1) for name, starts in self.positions.items()
        }
        self.recorded: set[int] = set()
        self.closed: set[int] = set()
        self.events: dict[str, dict[int, int]] = {}
        self.complete_from: int | None = None
        self.proofs: dict[str, tuple[list[int], list[int], list[int], list[int]]] = {}
        self.ordered_closes: list[int] | None = None

    def opened(self, name: str, at: int) -> None:
        events = self.events.setdefault(name, {})
        if at not in events:
            events[at] = 1
            self.proofs.clear()

    def unclosed_root(self, name: str, at: int) -> bool:
        # Only a full validated lexical scan can prove that no later closer
        # exists. Foreign closers disable the root-only balance shortcut.
        if self.complete_from is None or at < self.complete_from:
            return False
        if self.ordered_closes is None:
            self.ordered_closes = sorted(self.recorded)
        if name not in self.proofs:
            events = sorted(self.events.get(name, {}).items())
            closers = [offset for offset, value in events if value < 0]
            starts: list[int] = []
            prefix: list[int] = []
            total = 0
            for offset, value in events:
                if not closers or offset > closers[-1]:
                    break
                starts.append(offset)
                total += value
                prefix.append(total)
            minimum = prefix.copy()
            for index in range(len(minimum) - 2, -1, -1):
                minimum[index] = min(minimum[index], minimum[index + 1])
            self.proofs[name] = starts, prefix, minimum, closers
        starts, prefix, minimum, closers = self.proofs[name]
        if not closers or closers[-1] < at:
            return True
        last = closers[-1]
        total_closes = bisect_right(self.ordered_closes, last) - bisect_left(
            self.ordered_closes, at
        )
        root_closes = len(closers) - bisect_left(closers, at)
        if total_closes != root_closes:
            return False
        first = bisect_left(starts, at)
        before = prefix[first - 1] if first else 0
        return minimum[first] >= before

    def record(self, name: str, at: int) -> None:
        if at in self.recorded:
            return
        self.recorded.add(at)
        self.events.setdefault(name, {})[at] = -1
        self.proofs.clear()
        self.ordered_closes = None
        starts = self.positions[name]
        index = bisect_left(starts, at) + 1
        tree = self.trees[name]
        while index < len(tree):
            tree[index] += 1
            index += index & -index

    def contains(self, name: str, start: int, end: int) -> bool:
        starts = self.positions.get(name, ())
        if not starts:
            return False
        tree = self.trees[name]

        def prefix(index: int) -> int:
            count = 0
            while index:
                count += tree[index]
                index -= index & -index
            return count

        return prefix(bisect_left(starts, end)) > prefix(bisect_left(starts, start))


def html_end(
    text: str,
    start: int,
    *,
    siblings: bool,
    element_ends: dict[int, int] | None = None,
    element_states: dict[tuple[int, str], int] | None = None,
    bound_index: _ClosingIndex | None = None,
) -> int:
    """Bound streamed HTML using element or sibling ownership."""
    if element_ends is None:
        element_ends = {}
    if not siblings and start in element_ends:
        return element_ends[start]
    if element_states is None:
        element_states = {}
    if bound_index is None:
        bound_index = _ClosingIndex(text)
    states: list[tuple[int, str]] = []
    stack: list[tuple[str, int]] = []
    counts = {}
    at = start
    completed = start
    seen = False

    def finish(end: int) -> int:
        if end == len(text) and at >= len(text):
            bound_index.complete_from = (
                min(start, bound_index.complete_from)
                if bound_index.complete_from is not None
                else start
            )
        for state in states:
            element_states[state] = end
        return end

    def unfinished() -> int:
        # Roots still active in this exact parser stack are also unclosed when
        # queried independently. Descendants popped by another name are not cached.
        for _, opening in stack:
            element_ends[opening] = len(text)
        return finish(len(text))

    while at < len(text):
        if not siblings and len(stack) == 1:
            if bound_index.unclosed_root(stack[0][0], at):
                element_ends[stack[0][1]] = len(text)
                return finish(len(text))
            state = at, stack[0][0]
            if state in element_states:
                end = element_states[state]
                element_ends[stack[0][1]] = end
                return finish(end)
            states.append(state)
        if stack and stack[-1][0] in RAW_TEXT:
            found = re.compile(
                r"</" + stack[-1][0] + r"(?=[\s/>])", re.IGNORECASE
            ).search(text, at)
            if found is None:
                return unfinished()
            at = found.start()
        if not stack and seen:
            if not siblings:
                return finish(completed)
            while at < len(text) and text[at].isspace():
                at += 1
            if at == len(text):
                return unfinished()
            if text[at] != "<":
                return finish(completed)
        if text[at] != "<":
            at = text.find("<", at)
            if at < 0:
                return unfinished()
        token = markup(text, at)
        if token.kind == "incomplete":
            return unfinished()
        if token.kind == "invalid":
            if not stack and seen:
                return finish(completed)
            at += 1
            continue
        if (
            not stack
            and seen
            and token.kind == "tag"
            and not token.closing
            and (token.name in NATIVE_ROOTS or video_end(text, at) is not None)
        ):
            return finish(completed)
        if token.kind == "tag" and token.closing:
            bound_index.record(token.name, at)
        if (
            not siblings
            and len(stack) == 1
            and token.kind == "tag"
            and not token.closing
            and at in bound_index.closed
            and (
                token.name == stack[0][0]
                or not bound_index.contains(stack[0][0], token.end, element_ends[at])
            )
        ):
            # A validated child cannot close the sole parent inside this span.
            at = element_ends[at]
            continue
        seen = True
        token_start = at
        at = token.end
        if token.kind == "tag":
            if token.closing and counts.get(token.name, 0):
                while stack:
                    popped, opening = stack.pop()
                    counts[popped] -= 1
                    if popped == token.name:
                        element_ends[opening] = token.end
                        bound_index.closed.add(opening)
                        break
            elif (
                not token.closing
                and not token.self_closing
                and token.name not in VOID_TAGS
            ):
                bound_index.opened(token.name, token_start)
                stack.append((token.name, token_start))
                counts[token.name] = counts.get(token.name, 0) + 1
        if not stack:
            completed = at
    return unfinished()


def widget_resources(
    text: str,
    start: int,
    end: int,
    element_ends: dict[int, int] | None = None,
    element_states: dict[tuple[int, str], int] | None = None,
    bound_index: _ClosingIndex | None = None,
) -> bool:
    """Check whether native HTML contains sandbox resource markup."""
    at = start
    while at < end:
        if text[at] != "<":
            at += 1
            continue
        token = markup(text, at)
        if token.kind == "tag" and not token.closing:
            if token.name in WIDGET_ROOTS and video_end(text, at) is None:
                return True
            if token.name in RAW_TEXT:
                at = html_end(
                    text,
                    at,
                    siblings=False,
                    element_ends=element_ends,
                    element_states=element_states,
                    bound_index=bound_index,
                )
                continue
        if token.kind == "incomplete":
            break
        at = token.end if token.kind != "invalid" else at + 1
    return False


def _merge(spans: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    return merged


def sandbox_events(
    text: str,
    start: int,
    end: int,
    element_ends: dict[int, int] | None = None,
    element_states: dict[tuple[int, str], int] | None = None,
    bound_index: _ClosingIndex | None = None,
    custom_ends: tuple[int, ...] | None = None,
) -> list[Run]:
    """Return custom-button tails to ordinary Markdown ownership."""
    cursor = start
    at = start
    events = []
    if custom_ends is None:
        custom_ends = tuple(
            match.end()
            for match in re.finditer(
                r"</custom-button-after-content\s*>", text, re.IGNORECASE
            )
        )
    first = bisect_right(custom_ends, start)
    if first >= len(custom_ends) or custom_ends[first] > end:
        return [Run(start, end, "sandbox")] if start < end else []
    while at < end:
        if text[at] != "<":
            at += 1
            continue
        token = markup(text, at)
        if token.kind == "incomplete":
            break
        if token.kind == "tag" and not token.closing:
            if token.name == "custom-button-after-content":
                closing = min(
                    html_end(
                        text,
                        at,
                        siblings=False,
                        element_ends=element_ends,
                        element_states=element_states,
                        bound_index=bound_index,
                    ),
                    end,
                )
                closing_index = bisect_left(custom_ends, closing)
                if (
                    closing_index < len(custom_ends)
                    and custom_ends[closing_index] == closing
                ):
                    if at > cursor:
                        events.append(Run(cursor, at, "sandbox"))
                    cursor = closing
                    at = closing
                    continue
            if token.name in RAW_TEXT:
                at = html_end(
                    text,
                    at,
                    siblings=False,
                    element_ends=element_ends,
                    element_states=element_states,
                    bound_index=bound_index,
                )
                continue
        at = token.end if token.kind != "invalid" else at + 1
    if cursor < end:
        events.append(Run(cursor, end, "sandbox"))
    return events


def build_ownership(
    text: str,
    *,
    protected: Iterable[tuple[int, int]] = (),
    html_bounds: Mapping[int, int] | None = None,
    controls: Iterable[int] = (),
    code_starts: Iterable[int] = (),
    metadata: Iterable[tuple[int, int]] = (),
    variables: Iterable[tuple[int, int]] = (),
    code_ranges: Iterable[tuple[int, int]] = (),
) -> RunIndex:
    """Build source scopes once from existing raw scanner ownership metadata."""
    protected = _merge(protected)
    protected_starts = [start for start, _ in protected]
    metadata = _merge(metadata)
    metadata_starts = [start for start, _ in metadata]
    variables = _merge(variables)
    variable_starts = [start for start, _ in variables]
    code_ranges = _merge(code_ranges)
    code_range_starts = [start for start, _ in code_ranges]
    fragments = FragmentIndex(text)
    element_ends: dict[int, int] = {}
    element_states: dict[tuple[int, str], int] = {}
    bound_index = _ClosingIndex(text)
    custom_ends = tuple(
        match.end()
        for match in re.finditer(
            r"</custom-button-after-content\s*>", text, re.IGNORECASE
        )
    )
    html_bounds = html_bounds or {}
    controls = sorted(controls)
    code_starts = frozenset(code_starts)
    events = []
    at = 0
    literal = 0
    while at < len(text):
        while literal < len(protected) and protected[literal][1] <= at:
            literal += 1
        if literal < len(protected) and protected[literal][0] <= at:
            at = protected[literal][1]
            continue
        if text[at] != "<":
            at += 1
            continue
        token = markup(text, at)
        root = token.name if token.kind == "tag" and not token.closing else ""
        doctype = DOCTYPE.match(text, at) is not None
        if root in SANDBOX_ROOTS or doctype:
            video = video_end(text, at)
            native = root in NATIVE_ROOTS
            end = (
                video
                if video is not None
                else html_end(
                    text,
                    at,
                    siblings=not native,
                    element_ends=element_ends,
                    element_states=element_states,
                    bound_index=bound_index,
                )
            )
            boundary = html_bounds.get(at)
            if (
                boundary is not None
                and bisect_right(controls, boundary - 1) < len(controls)
                and end > boundary
            ):
                end = boundary
            immediate = video is not None or (
                native
                and not widget_resources(
                    text, at, end, element_ends, element_states, bound_index
                )
            )
            if immediate:
                events.append(Run(at, end, "stable"))
            else:
                events.extend(
                    sandbox_events(
                        text,
                        at,
                        end,
                        element_ends,
                        element_states,
                        bound_index,
                        custom_ends,
                    )
                )
            at = max(at + 1, end)
        elif token.kind == "tag" and not token.closing and token.name in {"svg", "img"}:
            at = (
                token.end
                if token.name == "img"
                else html_end(
                    text,
                    at,
                    siblings=False,
                    element_ends=element_ends,
                    element_states=element_states,
                    bound_index=bound_index,
                )
            )
        elif token.kind == "tag" and not token.closing and token.name in RAW_TEXT:
            at = html_end(
                text,
                at,
                siblings=False,
                element_ends=element_ends,
                element_states=element_states,
                bound_index=bound_index,
            )
        elif token.kind == "incomplete":
            break
        else:
            at = token.end if token.kind != "invalid" else at + 1
    runs = []
    cursor = 0
    stable = False

    def markdown_run(start: int, end: int, *, full_ast: bool) -> None:
        if end <= start:
            return
        if full_ast:
            runs.append(Run(start, end, "stable"))
            return
        previous = start
        cursor = start
        while (match := fragments.next(cursor, end)) is not None:
            left, right, fenced = match
            cursor = right
            # The UI rewinds an inert metadata match to its owner's end.  A
            # rejected inline-code match deliberately keeps the regex cursor.
            variable_index = bisect_right(variable_starts, left) - 1
            if variable_index >= 0 and left < variables[variable_index][1]:
                cursor = variables[variable_index][1]
                continue
            metadata_index = bisect_right(metadata_starts, left) - 1
            if metadata_index >= 0 and left < metadata[metadata_index][1]:
                cursor = metadata[metadata_index][1]
                continue
            if fenced and left not in code_starts:
                continue
            line_start = text.rfind("\n", start, left) + 1
            line_start = max(line_start, start)
            eligible = (
                re.fullmatch(r" {0,3}", text[line_start:left]) is not None
                if fenced
                else True
            )
            literal_index = bisect_right(protected_starts, left) - 1
            owned = literal_index >= 0 and left < protected[literal_index][1]
            if not eligible or (
                owned and not (fenced and right <= protected[literal_index][1])
            ):
                continue
            if left > previous:
                runs.append(Run(previous, left, "markdown"))
            runs.append(Run(left, right, "code" if fenced else "svg"))
            previous = right

        # The UI handles streaming SVG/mermaid tails after complete fragments.
        # Searches are scoped to this same non-sandbox Markdown run.
        def inside(
            spans: list[tuple[int, int]], starts: list[int], offset: int
        ) -> bool:
            index = bisect_right(starts, offset) - 1
            return index >= 0 and offset < spans[index][1]

        svg = text.rfind("<svg", start, end)
        svg_close = text.rfind("</svg>", start, end)
        if svg < 0 or (svg_close >= 0 and svg_close > svg):
            if text.startswith("<sv", end - 3, end):
                svg = end - 3
            elif text.startswith("<s", end - 2, end):
                svg = end - 2
        incomplete_code = text.find("```", previous, end)
        in_code_tail = incomplete_code >= 0 and incomplete_code < svg
        if (
            svg >= previous
            and not in_code_tail
            and not inside(code_ranges, code_range_starts, svg)
            and not inside(metadata, metadata_starts, svg)
            and not inside(variables, variable_starts, svg)
            and (svg_close < 0 or svg_close < svg)
        ):
            if svg > previous:
                runs.append(Run(previous, svg, "markdown"))
            runs.append(Run(svg, end, "svg"))
            return
        mermaid = text.rfind("```mermaid", start, end)
        mermaid_line = text.rfind("\n", start, mermaid) + 1
        if (
            mermaid >= previous
            and mermaid == incomplete_code
            and mermaid in code_starts
            and re.fullmatch(r" {0,3}", text[max(start, mermaid_line) : mermaid])
            is not None
            and not inside(metadata, metadata_starts, mermaid)
            and not inside(variables, variable_starts, mermaid)
        ):
            if mermaid > previous:
                runs.append(Run(previous, mermaid, "markdown"))
            runs.append(Run(mermaid, end, "code"))
            return
        if previous < end:
            runs.append(Run(previous, end, "markdown"))

    for event in events:
        if event.kind == "stable":
            stable = True
            continue
        markdown_run(cursor, event.start, full_ast=stable)
        runs.append(event)
        cursor = event.end
        stable = False
    markdown_run(cursor, len(text), full_ast=stable)
    return RunIndex(runs)
