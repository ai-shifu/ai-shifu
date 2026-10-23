"""Small continuation witnesses for the document parser used by narration streams."""

from __future__ import annotations

import re
from string import punctuation

from .document_blocks import container_content_start, fence_opening, physical_lines
from .marker_context import analyze_marker_context
from .stream_html_context import pending_html_prefix

_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]|$)")


def _gap(text: str) -> str:
    """Keep physical-line context without keeping the narration on that line."""
    if not text:
        return ""
    lines = re.split(r"\r\n|[\r\n]", text)

    def line(value: str) -> str:
        if not value.strip(" \t\r"):
            return "    " if "\t" in value or len(value) >= 4 else value
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


def _raw_prefix(text: str, tag: str, closed: bool) -> str:
    if closed:
        return f"<{tag}></{tag}>x"
    tail = text[text.rfind("<") :].lower() if "<" in text else ""
    closing = "</" + tag
    if closing.startswith(tail):
        suffix = tail
    elif tail.startswith(closing) and not tail[len(closing) :].strip(" \t\r\n"):
        suffix = closing + " "
    else:
        suffix = ""
    return f"<{tag}>x" + suffix


def _block_tail(text: str) -> str:
    """Retain a partial blank line, including a physical ending split across chunks."""
    tail = physical_lines(text)[-1]
    value = text[tail.start :]
    if not value.strip(" \t"):
        return "\n" + value[:4] if tail.start else value[:4]
    return "x"


def _container_prefix(text: str, state: tuple[str, int, tuple[int, ...]]) -> str:
    marker, width, steps = state
    opening = (
        "".join("> " if step == 0 else "-" + " " * (step - 1) for step in steps)
        + marker * width
    )
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


def compact_marker_context(source: str) -> str:
    """Preserve source-ordered unfinished syntax using bounded content witnesses."""
    context = analyze_marker_context(source, final=False)
    records: list[tuple[int, int, str]] = [
        (at, at + len(run), run)
        for at, run in (*context.unmatched_backticks, *context.unmatched_math)
    ]
    for at, (image, active) in zip(
        context.pending_label_starts, context.pending_labels, strict=True
    ):
        records.append(
            (
                at,
                at + 1,
                ("!" if image else "") + "[" + ("[x](u)" if not active else ""),
            )
        )
    if context.pending_resource_opener:
        start = context.pending_resource_label_start
        start = len(source) - 1 if start is None else start
        label = "x".join(value for at, _, value in records if at >= start) or "x"
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

    primary: tuple[int, int, str] | None = None
    if (
        context.pending_reference_start is not None
        and context.pending_reference_body_start is not None
    ):
        start = context.pending_reference_start
        body = context.pending_reference_body_start
        resource = _resource_prefix("(" + source[body:], tokens(body))
        if resource is not None:
            primary = (start, len(source), "[x]: " + resource[1:])
    if (
        primary is None
        and context.pending_block_start is not None
        and context.pending_html_closing_line
    ):
        # A complete HTML block token owns the rest of its closing physical line.
        primary = (context.pending_block_start, len(source), "<!--x-->x")
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
        primary = (start, len(source), "<div>x" + _block_tail(source[start:]))
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
            ),
        )
    elif primary is None and context.pending_html_start is not None:
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
        html = pending_html_prefix(html_source, context.pending_html_start)
        if html is not None:
            start, _ = html
            # The CDATA opener itself supplies its two brackets on every replay.
            body_start = start + 9 if source.startswith("<![CDATA[", start) else start
            html = pending_html_prefix(html_source, start, tokens=tokens(body_start))
            if html is not None:
                primary = (start, len(source), html[1])
    if context.pending_resource_start is not None and (
        primary is None or context.pending_resource_start < primary[0]
    ):
        start = context.pending_resource_start
        resource = _resource_prefix(source[start:], tokens(start))
        if resource is not None:
            label_start = context.pending_resource_label_start
            label_start = start - 1 if label_start is None else label_start
            label = (
                "x".join(value for at, _, value in records if label_start <= at < start)
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
    if primary is not None:
        records = [record for record in records if record[0] < primary[0]]
        records.append(primary)
    records.sort()
    # Completed literal syntax must not become a fresh opener when old prose is discarded.
    gap_characters = list(source)
    for start, end in context.literals:
        for offset in range(start, end):
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
    at = 0
    for start, end, witness in records:
        if start < at:
            continue
        pieces.extend((_gap(gap_source[at:start]), witness))
        at = end
    pieces.append(_gap(gap_source[at:]))
    return "".join(pieces)
