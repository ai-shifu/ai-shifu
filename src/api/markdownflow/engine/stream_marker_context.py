"""Small continuation witnesses for the document parser used by narration streams."""

from __future__ import annotations

import re
from bisect import bisect_right
from string import punctuation

from markdownflow.syntax.parser.document_blocks import (
    compact_angle_autolink_prefix,
    container_content_start,
    container_opening,
    container_opening_info,
    fence_opening,
    indentation,
    physical_lines,
)
from markdownflow.syntax.parser.marker_context import analyze_marker_context
from markdownflow.syntax.variable_names import read_variable_marker

from .stream_html_context import pending_html_prefix

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]|$)")


def _gap(text: str) -> str:
    """Keep physical-line context without keeping the narration on that line."""
    if not text:
        return ""
    lines = re.split(r"\r\n|[\r\n]", text)

    def line(value: str) -> str:
        content, steps = container_opening(value)
        if steps:
            return value[:content] + line(value[content:])
        if not value.strip(" \t\r"):
            return "    " if "\t" in value or len(value) >= 4 else value
        # Extra padding can precede a heading inside an active list. Keeping its
        # spelling also remains indented code when there is no list container.
        if match := re.match(r"^([ \t]+)(#{1,6})(?:[ \t]|$)", value):
            return match.group(1) + match.group(2) + " x "
        if value.startswith("    ") or re.match(r"^ {0,3}\t", value):
            return "    x"
        if (
            fence_opening(value + "```") is not None
            or fence_opening(value + " ```") is not None
        ):
            return value
        if re.fullmatch(r" {0,3}[0-9]{1,9}[.)]?", value):
            return value
        if re.fullmatch(r" {0,3}(?:[-*_][ \t]*)+", value):
            symbols = value.strip().replace(" ", "").replace("\t", "")
            if len(set(symbols)) == 1:
                return symbols[:3] + (" " if value.endswith((" ", "\t")) else "")
        if re.fullmatch(r" {0,3}=+[ \t]*", value):
            return "="
        if match := _HEADING.match(value):
            if not value.lstrip(" ").strip("#"):
                return value
            return match.group(1) + " x "
        return "x "

    tail = line(lines[-1])
    if len(lines) > 1:
        previous = line(lines[-2])
        tail = previous + "\n" + tail
        if len(lines) > 2 and not previous:
            tail = "\n" + tail
        elif len(lines) > 2 and previous == "=" and lines[-3].strip(" \t\r"):
            tail = "# x\n" + line(lines[-1])
    if (len(text) - len(text.rstrip("\\"))) % 2:
        tail += "\\"
    if text.endswith("!"):
        before = text[:-1]
        if (len(before) - len(before.rstrip("\\"))) % 2:
            tail += "\\"
        tail += "!"
    return tail


def _resource_prefix(text: str, tokens: str) -> str | None:
    """Read a viable resource prefix, remembering grammar state rather than URL/title text."""
    state = "space"
    depth = 0
    quote = ""
    escaped = False
    newline = False
    spaced = False
    destination = "u"
    for character in text[1:].replace("\r\n", "\n").replace("\r", "\n"):
        if escaped:
            escaped = False
            if character in punctuation:
                continue
        if character == "\\" and state in ("bare", "angle", "title"):
            escaped = True
            continue
        if state in ("space", "after_destination", "after_title"):
            if character in " \t\r\n":
                if character == "\n":
                    if newline:
                        return None
                    newline = True
                spaced = True
                continue
            newline = False
            if state == "after_title":
                return None  # A closing outer parenthesis would already be complete.
            if state == "after_destination":
                if not spaced or character not in "\"'(":
                    return None
                quote = ")" if character == "(" else character
                state = "title"
                continue
            if character == "<":
                state = "angle"
                destination = "<u"
                continue
            state = "bare"
        if state == "angle":
            if character in "<\r\n":
                return None
            if character == ">":
                state = "after_destination"
                destination = "<u>"
                spaced = False
            continue
        if state == "bare":
            if character in " \t\r\n":
                state = "after_destination"
                destination = "u" + "(" * depth
                if depth:
                    return None
                spaced = True
                newline = character == "\n"
            elif character == "(":
                depth += 1
                if depth > 32:
                    return None
            elif character == ")":
                if not depth:
                    return None
                depth -= 1
            elif ord(character) < 32 or character == "\x7f":
                return None
        elif state == "title":
            if character == quote:
                state = "after_title"
                newline = False
            elif character == "\n":
                if newline:
                    return None
                newline = True
            elif character not in " \t\r":
                newline = False
    kept = tokens or "x"
    slash = "\\" if escaped else ""
    if state == "space":
        return "(" + ("\n" if newline else " ")
    if state == "angle":
        return "(<" + kept + slash
    if state == "bare":
        return "(" + kept + "(" * depth + slash
    if state == "after_destination":
        destination = "<" + kept + ">" if destination.startswith("<") else kept
        return "(" + destination + ("\n" if newline else " " if spaced else "")
    opening = "(" if quote == ")" else quote
    if state == "title":
        return (
            "(" + destination + " " + opening + kept + slash + ("\n" if newline else "")
        )
    return "(" + destination + " " + opening + kept + quote + ("\n" if newline else " ")


def _raw_prefix(text: str, tag: str, closed: bool, steps: tuple[int, ...]) -> str:
    tail = text[text.rfind("<") :].lower() if "<" in text else ""
    closing = "</" + tag
    if closing.startswith(tail):
        suffix = tail
    elif tail.startswith(closing) and not tail[len(closing) :].strip(" \t\r\n"):
        suffix = closing + " "
    else:
        suffix = ""
    opening = _container_opening(steps, text) + f"<{tag}>x"
    lines = physical_lines(text)
    if len(lines) == 1:
        return opening + (f"</{tag}>x" if closed else suffix)
    value = text[lines[-1].start :]
    content = container_content_start(value, steps)
    if content is None:
        return opening + "\n" + value
    return (
        opening
        + "\n"
        + value[:content]
        + (f"</{tag}>x" if closed else suffix or ("x" if value[content:] else ""))
    )


def _block_tail(text: str) -> str:
    """Retain a partial blank line, including a physical ending split across chunks."""
    tail = physical_lines(text)[-1]
    value = text[tail.start :]
    if not value.strip(" \t"):
        return "\n" + value[:4] if tail.start else value[:4]
    return "x"


def _container_prefix(text: str, state: tuple[str, int, tuple[int, ...]]) -> str:
    marker, width, steps = state
    opening = _container_opening(steps, text) + marker * width
    continuation = "".join("> " if step == 0 else " " * step for step in steps)
    lines = physical_lines(text)
    if len(lines) == 1:
        return opening
    value = text[lines[-1].start :]
    content = container_content_start(value, steps)
    if content is None:
        tail = value  # A partial container prefix is already bounded by its steps.
    else:
        body = value[content:]
        tail = value[:content] + (
            re.sub(r"[ \t]+", lambda match: match.group()[:4], body)
            if not body.strip(marker + " \t")
            else "x"
        )
    return opening + "\n" + continuation + "x\n" + tail


def _container_opening(steps: tuple[int, ...], text: str = "") -> str:
    if text:
        first = physical_lines(text)[0]
        value = text[: first.content_end]
        content, actual = container_opening(value)
        if actual == steps:
            return value[:content]
    pieces = []
    for step in steps:
        if step == 0:
            pieces.append("> ")
        elif step <= 5:
            pieces.append("-" + " " * (step - 1))
        else:
            # Ordered markers supply the width that a bullet cannot express:
            # padding after any Markdown list marker is limited to four columns.
            leading = max(0, step - 14)
            width = min(10, step - leading - 1)
            pieces.append(
                " " * leading
                + "1"
                + "0" * (width - 2)
                + "."
                + " " * (step - leading - width)
            )
    return "".join(pieces)


def container_paragraph_witness(steps: tuple[int, ...]) -> str | None:
    """Return one paragraph line that leaves exactly `steps` open, or None.

    A line read after it finds the same open containers and an open paragraph
    in them, which is all the block state a plain paragraph line carries on.
    """
    opening = _container_opening(steps)
    content, actual, virtual = container_opening_info(opening + "x")
    if actual != steps or virtual or content != len(opening):
        return None
    return opening + "x\n"


def _indented_prefix(text: str, steps: tuple[int, ...]) -> str:
    opening = _container_opening(steps, text) + "    x"
    lines = physical_lines(text)
    if len(lines) == 1:
        return opening
    value = text[lines[-1].start :]
    content = container_content_start(value, steps)
    if content is None:
        return opening + "\n" + value
    body = value[content:]
    return (
        opening
        + "\n"
        + value[:content]
        + (body[:4] if not body.strip(" \t") else "    x")
    )


def _contained_block_tail(text: str, steps: tuple[int, ...]) -> str:
    """Keep a partial continuation prefix while discarding HTML body prose."""
    if not steps:
        return _block_tail(text)
    lines = physical_lines(text)
    if len(lines) == 1:
        return "x"
    value = text[lines[-1].start :]
    content = container_content_start(value, steps)
    if content is None:
        return "\n" + value
    body = value[content:]
    return "\n" + value[:content] + (body[:4] if not body.strip(" \t") else "x")


def _reference_prefix(
    source: str, body: int, steps: tuple[int, ...], tokens: str
) -> str | None:
    """Project only reference padding for its existing resource-state reader."""
    text = source[body:]
    projected: list[str] = []
    partial = ""
    for index, line in enumerate(physical_lines(text)):
        value = text[line.start : line.content_end]
        if index and steps:
            content = container_content_start(value, steps)
            if content is not None:
                value = value[content:]
            elif (
                line.end == len(text)
                and container_content_start(value, steps, partial=True) is not None
            ):
                partial = value
                break
        projected.append(value + text[line.content_end : line.end])
    resource = _resource_prefix("(" + "".join(projected), tokens)
    if resource is None:
        return None
    continuation = "".join("> " if step == 0 else " " * step for step in steps)
    value = _container_opening(steps) + "[x]: " + resource[1:]
    if partial:
        return value + partial
    return re.sub(r"\n(?=.)", lambda _: "\n" + continuation, value)


def _special_container_html_prefix(source: str, start: int) -> str | None:
    """Keep a container's partial next-line prefix outside an unfinished HTML token."""
    text = source[start:]
    lines = physical_lines(text)
    if len(lines) == 1:
        return None
    line_start = max(source.rfind("\n", 0, start), source.rfind("\r", 0, start)) + 1
    before = source[line_start:start]
    content, steps, virtual = container_opening_info(before)
    _, columns = indentation(before, content, virtual)
    if not steps or columns >= 4 or before[content:].strip(" \t"):
        return None
    if text.startswith("<!--"):
        opening, closing = "<!--x", "-->"
    elif text.startswith("<?"):
        opening, closing = "<?x", "?>"
    elif text.startswith("<![CDATA["):
        opening, closing = "<![CDATA[x", "]]>"
    elif re.match(r"<![A-Z]", text):
        opening, closing = "<!Ax", ">"
    else:
        return None
    value = text[lines[-1].start :]
    content = container_content_start(value, steps, partial=True)
    if content is None:
        return None
    suffix = next(
        (
            closing[:width]
            for width in range(len(closing) - 1, 0, -1)
            if text.endswith(closing[:width])
        ),
        "",
    )
    body = "x" + suffix if value[content:] else ""
    return before + opening + "\n" + value[:content] + body


def _autolink_prefix(text: str, tokens: str) -> str:
    """Keep the bounded lexical state of an already validated angle-link prefix."""
    if text.endswith("{") and not tokens.endswith("{"):
        before = text[:-1]
        escaped = (len(before) - len(before.rstrip("\\"))) % 2
        tokens += ("\\" if escaped else "") + "{"
    if (len(text) - len(text.rstrip("\\"))) % 2:
        tokens += "\\"
    if text.endswith("!"):
        before = text[:-1]
        escaped = (len(before) - len(before.rstrip("\\"))) % 2
        tokens += ("\\" if escaped else "") + "!"
    return compact_angle_autolink_prefix(text, 0, tokens=tokens) or text


def pending_autolink_is_primary(source: str, start: int) -> bool:
    """Keep viable HTML constructs in their established continuation state."""
    return not (
        source.startswith(("<!", "<?", "</"), start)
        and pending_html_prefix(source, start) is not None
    )


def _reference_marker_spans(source: str, body: int) -> list[tuple[int, int]]:
    """Read raw marker ownership only inside an already viable reference tail."""
    spans: list[tuple[int, int]] = []
    at = body
    while (start := source.find("{{", at)) >= 0:
        before = start
        while before and source[before - 1] == "\\":
            before -= 1
        if (start - before) % 2:
            at = start + 1
            continue
        marker = read_variable_marker(source, start)
        spans.append((start, marker.end if marker is not None else len(source)))
        if marker is None:
            break
        at = marker.end
    return spans


def pending_literal_context(
    source: str, *, reference_markers: list[tuple[int, int]] | None = None
) -> tuple[int, str] | None:
    """Keep viable outer literal grammar until a raw marker can be classified."""
    context = analyze_marker_context(source, final=False)
    starts: list[int] = []
    if (
        context.pending_reference_start is not None
        and context.pending_reference_body_start is not None
    ):
        body = context.pending_reference_body_start
        reference = _reference_prefix(source, body, context.pending_reference_steps, "")
        if reference is not None:
            starts.append(context.pending_reference_start)
            if reference_markers is not None:
                reference_markers.extend(_reference_marker_spans(source, body))
    if context.pending_autolink_start is not None:
        start = context.pending_autolink_start
        if compact_angle_autolink_prefix(source, start) is not None:
            starts.append(start)
    if context.pending_resource_start is not None:
        start = context.pending_resource_start
        if _resource_prefix(source[start:], "") is not None:
            starts.append(start)
    if context.pending_html_start is not None:
        # A false token cannot restart inside a marker that already owns its text.
        candidates = list(source)
        for start, end in [
            *context.literals,
            *((marker.start, marker.end) for marker in context.markers),
        ]:
            for at in range(start, min(end, len(source))):
                if candidates[at] == "<":
                    candidates[at] = "\x00"
        html = pending_html_prefix("".join(candidates), context.pending_html_start)
        if html is not None:
            starts.append(html[0])
    if not starts:
        return None
    return min(starts), compact_marker_context(source)


def compact_marker_context(
    source: str,
    *,
    label_counts: dict[int, int] | None = None,
    counts_out: dict[int, int] | None = None,
    lookahead: str = "",
) -> str:
    """Preserve source-ordered unfinished syntax using bounded content witnesses."""
    context = analyze_marker_context(source, final=False, label_counts=label_counts)
    # A held question/marker opener or CR can confirm an inline closer's width.
    # Replay that real next character only for an unresolved matching inline run;
    # block continuations must retain their existing physical-line EOF state.
    # These single suffixes cannot introduce a new context token to replay twice.
    following = lookahead[:1]
    if source.endswith(("`", "$")) and following in ("?", "{", "\r"):
        opening = len(source.rstrip(source[-1]))
        width = len(source) - opening
        unmatched = (
            context.unmatched_backticks if source[-1] == "`" else context.unmatched_math
        )
        if any(at < opening and len(run) == width for at, run in unmatched):
            context = analyze_marker_context(
                source + following, final=False, label_counts=label_counts
            )
    literal_starts = [start for start, _ in context.literals]

    def inside_literal(at: int) -> bool:
        index = bisect_right(literal_starts, at) - 1
        return index >= 0 and at < context.literals[index][1]

    records: list[tuple[int, int, str]] = [
        (at, at + len(run), run)
        for at, run in (*context.unmatched_backticks, *context.unmatched_math)
    ]
    records.extend(
        (marker.start, len(source), "{{" + ("}" if source.endswith("}") else ""))
        for marker in context.markers
        if not marker.complete and not inside_literal(marker.start)
    )
    label_records: dict[int, int] = {}
    label_values: dict[int, str] = {}
    for at, (image, active), count in zip(
        context.pending_label_starts,
        context.pending_labels,
        context.pending_label_counts,
        strict=True,
    ):
        label_records[at] = count
        label_values[at] = (
            ("!" if image else "") + "[" + ("[x](u)" if not active else "")
        )
        records.append(
            (
                at,
                at + 1,
                label_values[at],
            )
        )
    if context.pending_resource_opener:
        start = context.pending_resource_label_start
        start = len(source) - 1 if start is None else start
        label = "x".join(value for at, _, value in records if at > start) or "x"
        records = [
            (at, at if at == start and at in label_records else end, value)
            for at, end, value in records
        ]
        records.append(
            (
                start,
                len(source),
                ("!" if context.pending_resource_image else "") + "[" + label + "]",
            )
        )
    records.sort()

    def tokens(start: int) -> str:
        return "x".join(value for at, _, value in records if at >= start)

    def merge_labels(
        values: list[tuple[int, int, str]],
    ) -> list[tuple[int, int, str]]:
        merged: list[tuple[int, int, str]] = []
        for start, end, witness in values:
            if (
                start in label_records
                and merged
                and merged[-1][2] == witness
                and merged[-1][0] in label_records
            ):
                before, _, value = merged[-1]
                label_records[before] += label_records[start]
                merged[-1] = (before, end, value)
            else:
                merged.append((start, end, witness))
        return merged

    primary: tuple[int, int, str] | None = None
    autolink_counts: dict[int, int] = {}
    autolink_witness: str | None = None
    nested_autolink_witness: str | None = None
    if (
        context.pending_reference_start is not None
        and context.pending_reference_body_start is not None
    ):
        start = context.pending_reference_start
        body = context.pending_reference_body_start
        reference_tokens = tokens(body)
        if (
            _reference_prefix(source, body, context.pending_reference_steps, "")
            is not None
        ):
            spans = _reference_marker_spans(source, body)
            if spans and read_variable_marker(source, spans[-1][0]) is None:
                opening = spans[-1][0]
                if not any(at == opening for at, _, _ in records):
                    reference_tokens += "{{" + ("}" if source.endswith("}") else "")
            if source.endswith("{") and not reference_tokens.endswith("{"):
                before = source[:-1]
                escaped = (len(before) - len(before.rstrip("\\"))) % 2
                reference_tokens += ("\\" if escaped else "") + "{"
            elif (len(source) - len(source.rstrip("\\"))) % 2:
                reference_tokens += "\\"
        resource = _reference_prefix(
            source, body, context.pending_reference_steps, reference_tokens
        )
        if resource is not None:
            if source.endswith("\\"):
                # Reference padding may put a backslash at the first resource
                # character; retain its raw parity without the helper's filler.
                escaped = (len(source) - len(source.rstrip("\\"))) % 2
                resource = resource.rstrip("\\") + ("\\" if escaped else "")
            primary = (start, len(source), resource)
    if (
        primary is None
        and context.pending_block_start is not None
        and context.pending_html_closing_line
    ):
        # A complete HTML block token owns the rest of its closing physical line.
        start = context.pending_block_start
        primary = (
            start,
            len(source),
            _container_opening(context.pending_block_steps, source[start:])
            + "<!--x-->x",
        )
    if (
        primary is None
        and context.pending_block_start is not None
        and context.pending_indented_block
    ):
        start = context.pending_block_start
        primary = (
            start,
            len(source),
            _indented_prefix(source[start:], context.pending_block_steps),
        )
    if (
        primary is None
        and context.pending_block_start is not None
        and context.pending_container_fence is not None
    ):
        start = context.pending_block_start
        primary = (
            start,
            len(source),
            _container_prefix(source[start:], context.pending_container_fence),
        )
    elif (
        primary is None
        and context.pending_block_start is not None
        and context.pending_html_block
    ):
        start = context.pending_block_start
        if context.pending_html_name:
            # A native block-tag name at EOF may still gain another name
            # character. Its exact token is bounded by the native tag set.
            opening_source = source[start:]
            opening = opening_source[opening_source.index("<") :]
        elif context.pending_html_provisional:
            # Same-line body text can still invalidate a type-seven opener.
            opening = "<span>"
        else:
            opening = "<div>x" + _contained_block_tail(
                source[start:], context.pending_block_steps
            )
        primary = (
            start,
            len(source),
            _container_opening(context.pending_block_steps, source[start:]) + opening,
        )
    elif primary is None and (
        context.pending_raw_html_tag is not None
        and context.pending_html_start is not None
    ):
        start = context.pending_html_start
        primary = (
            start,
            len(source),
            _raw_prefix(
                source[start:],
                context.pending_raw_html_tag,
                context.pending_raw_html_closed,
                context.pending_block_steps,
            ),
        )
    elif primary is None and context.pending_autolink_start is not None:
        start = context.pending_autolink_start
        token_records = [record for record in records if record[0] >= start]
        if context.pending_resource_start is not None:
            resource_start = context.pending_resource_start
            resource = _resource_prefix(source[resource_start:], tokens(resource_start))
            label_start = context.pending_resource_label_start
            if (
                resource is not None
                and label_start is not None
                and label_start >= start
            ):
                token_records = [
                    (at, at if at == label_start else end, value)
                    for at, end, value in token_records
                    if at < label_start or (at == label_start and at in label_records)
                ]
                token_records.append(
                    (
                        label_start,
                        len(source),
                        ("!" if context.pending_resource_image else "")
                        + "[x]"
                        + resource,
                    )
                )
                token_records.sort()
        token_records = merge_labels(token_records)
        token_parts: list[str] = []
        token_counts: dict[int, int] = {}
        length = 0
        for at, _, value in token_records:
            if token_parts:
                length += 1
            if value == label_values.get(at):
                token_counts[length + value.index("[")] = label_records[at]
            token_parts.append(value)
            length += len(value)
        pending_tokens = "x".join(token_parts)
        if pending_autolink_is_primary(source, start):
            witness = _autolink_prefix(source[start:], pending_tokens)
        else:
            html = pending_html_prefix(source, start, tokens=pending_tokens)
            witness = (
                html[1]
                if html is not None
                else _autolink_prefix(source[start:], pending_tokens)
            )
        nested_autolink_witness = witness
        if token_counts:
            offset = witness.rfind(pending_tokens)
            if offset >= 0:
                autolink_counts = {
                    offset + at: count for at, count in token_counts.items()
                }
                autolink_witness = witness
        primary = (start, len(source), witness)
        if (
            context.pending_html_start is not None
            and context.pending_html_start < start
        ):
            # A pending token can contain a URI prefix. Preserve both native
            # lexers: closing the outer token makes its markers literal, while
            # an outer failure must still replay the inner URI's own boundary.
            html = pending_html_prefix(source, context.pending_html_start)
            if html is not None and html[0] < start:
                html_start = html[0]
                outer_tokens = "x".join(
                    [value for at, _, value in records if html_start <= at < start]
                    + [witness]
                )
                outer = pending_html_prefix(source, html_start, tokens=outer_tokens)
                if outer is not None:
                    # The inner lexer owns the append position. The HTML
                    # helper's filler must not split '{{' or extend a URI scheme.
                    outer_witness = outer[1]
                    insertion = outer_witness.rfind(outer_tokens + "x")
                    if insertion >= 0:
                        padding = insertion + len(outer_tokens)
                        outer_witness = (
                            outer_witness[:padding] + outer_witness[padding + 1 :]
                        )
                    primary = (html_start, len(source), outer_witness)
                    if autolink_counts and autolink_witness is not None:
                        offset = outer_witness.rfind(autolink_witness)
                        if offset >= 0:
                            autolink_counts = {
                                offset + at: count
                                for at, count in autolink_counts.items()
                            }
                            autolink_witness = outer_witness
    elif primary is None and context.pending_html_start is not None:
        contained = _special_container_html_prefix(source, context.pending_html_start)
        if contained is not None:
            start = context.pending_html_start
            line_start = (
                max(source.rfind("\n", 0, start), source.rfind("\r", 0, start)) + 1
            )
            primary = (line_start, len(source), contained)
        # A false earlier candidate must not restart inside an already-owned marker/code span.
        candidates = list(source)
        for start, end in [
            *context.literals,
            *((marker.start, marker.end) for marker in context.markers),
        ]:
            for at in range(start, end):
                if candidates[at] == "<":
                    candidates[at] = "\x00"
        html_source = "".join(candidates)
        html = (
            pending_html_prefix(html_source, context.pending_html_start)
            if primary is None
            else None
        )
        if html is not None:
            start, _ = html
            # The CDATA opener itself supplies its two brackets on every replay.
            body_start = start + 9 if source.startswith("<![CDATA[", start) else start
            html = pending_html_prefix(html_source, start, tokens=tokens(body_start))
            if html is not None:
                contained = _special_container_html_prefix(source, start)
                if contained is not None:
                    line_start = (
                        max(source.rfind("\n", 0, start), source.rfind("\r", 0, start))
                        + 1
                    )
                    primary = (line_start, len(source), contained)
                else:
                    primary = (start, len(source), html[1])
    if context.pending_resource_start is not None and (
        primary is None or context.pending_resource_start < primary[0]
    ):
        start = context.pending_resource_start
        resource_tokens = tokens(start)
        shared_angle = False
        if (
            nested_autolink_witness is not None
            and context.pending_autolink_start is not None
        ):
            angle = context.pending_autolink_start
            destination = start + 1
            while destination < len(source) and source[destination] in " \t\r\n":
                destination += 1
            if destination == angle:
                shared_angle = True
                # The resource's angle opener is also the URI's opener. Keep
                # the scheme once, rather than replaying an invalid nested '<'.
                resource_tokens = nested_autolink_witness[1:]
        resource = _resource_prefix(source[start:], resource_tokens)
        if resource is not None:
            if nested_autolink_witness == "<" and shared_angle:
                # An empty angle body must stay empty until its first real
                # character arrives; padding would alter the 32-character limit.
                resource = "(<"
            label_start = context.pending_resource_label_start
            label_start = start - 1 if label_start is None else label_start
            label = (
                "x".join(
                    value
                    for at, _, value in records
                    if label_start <= at < start
                    and not (at == label_start and at in label_records)
                )
                or "x"
            )
            primary = (
                label_start,
                len(source),
                ("!" if context.pending_resource_image else "")
                + "["
                + label
                + "]"
                + resource,
            )
            if autolink_counts and autolink_witness is not None:
                offset = primary[2].rfind(autolink_witness)
                if offset >= 0:
                    autolink_counts = {
                        offset + at: count for at, count in autolink_counts.items()
                    }
                    autolink_witness = primary[2]
    if primary is not None:
        records = [
            (at, at if at == primary[0] else end, value)
            for at, end, value in records
            if at < primary[0] or (at == primary[0] and at in label_records)
        ]
        records.append(primary)
    records.sort()
    # Repeated unresolved labels need a counter, not one replayed character per
    # nesting level. No source text or future closing bracket is discarded.
    records = merge_labels(records)
    # Completed literal syntax must not become a fresh opener when old prose is discarded.
    # A complete marker's name is opaque text: its lines carry no Markdown syntax.
    gap_characters = list(source)
    for start, end in (
        *context.literals,
        *((marker.start, marker.end) for marker in context.markers if marker.complete),
    ):
        for offset in range(start, min(end, len(source))):
            if gap_characters[offset] not in " \t\r\n":
                gap_characters[offset] = "x"
    # Confirmed block endings permit indented code on the next physical line.
    for end in context.indent_restart_after:
        if end < len(source):
            start = max(source.rfind("\n", 0, end), source.rfind("\r", 0, end)) + 1
            if start < end:
                gap_characters[start:end] = "#" + " " * (end - start - 1)
    gap_source = "".join(gap_characters)
    pieces: list[str] = []
    length = 0
    if counts_out is not None:
        counts_out.clear()
    at = 0
    for start, end, witness in records:
        if start < at:
            continue
        gap = _gap(gap_source[at:start])
        pieces.extend((gap, witness))
        if counts_out is not None and witness == label_values.get(start):
            counts_out[length + len(gap) + witness.index("[")] = label_records[start]
        if counts_out is not None and witness == autolink_witness:
            counts_out.update(
                (length + len(gap) + offset, count)
                for offset, count in autolink_counts.items()
            )
        length += len(gap) + len(witness)
        at = end
    pieces.append(_gap(gap_source[at:]))
    return "".join(pieces)
