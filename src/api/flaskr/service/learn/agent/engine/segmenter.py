"""Streaming segmenter for listen mode.

Turns a stream of model text into visuals and narration. A visual is a raw HTML block (nested
tags tracked until the root closes, with a directly following `<style>` block absorbed), a
fenced code block (html/svg/mermaid/other), a Markdown image line, or a Markdown table.
Everything else is narration, emitted line by line so TTS can start early.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .events import Visual

_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})\s*([\w+-]*)\s*$")


def _closes_fence(line: str, opening: str) -> bool:
    """Report whether this line closes a fence opened with `opening`.

    It must be the same marker, at least as long as the opener, and carry nothing else.
    """
    stripped = line.strip()
    return len(stripped) >= len(opening) and stripped == opening[0] * len(stripped)


_HTML_OPEN = re.compile(
    r"^\s*<(div|section|article|figure|table|svg|main|aside|header|footer)\b",
    re.IGNORECASE,
)
_STYLE_OPEN = re.compile(r"^\s*<(style|script)\b", re.IGNORECASE)
_STYLE_CLOSE = re.compile(r"</(style|script)\s*>", re.IGNORECASE)
_IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
_VOID_TAGS = {
    "br",
    "hr",
    "img",
    "input",
    "meta",
    "link",
    "source",
    "wbr",
    "area",
    "base",
    "col",
    "embed",
    "param",
    "track",
}


if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class Narration:
    """Spoken text between two visuals."""

    text: str


_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPH = re.compile(r"(\*\*|__)(.+?)\1|(?<!\w)([*_])(?!\s)(.+?)(?<!\s)\3(?!\w)")
_MD_CODE = re.compile(r"`([^`]*)`")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_MD_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_MD_QUOTE = re.compile(r"^\s*>\s?")


def plain_narration(line: str) -> str:
    """Narration as it should be read aloud / shown as a caption: markdown markers removed."""
    keep_nl = line.endswith("\n")
    t = line.rstrip("\n")
    t = _MD_HEADING.sub("", t)
    t = _MD_QUOTE.sub("", t)
    t = _MD_BULLET.sub("", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _MD_CODE.sub(r"\1", t)
    t = _MD_EMPH.sub(lambda m: m.group(2) if m.group(2) is not None else m.group(4), t)
    t = t.replace("~~", "")
    return t + ("\n" if keep_nl else "")


SegmentPiece = Visual | Narration


def _tag_delta(line: str, root: str) -> int:
    """Net change in nesting depth for `root` tags on this line."""
    opens = len(re.findall(rf"<{root}\b[^>]*?(?<!/)>", line, re.IGNORECASE))
    closes = len(re.findall(rf"</{root}\s*>", line, re.IGNORECASE))
    return opens - closes


@dataclass
class Segmenter:
    """Splits a listen-mode stream into visuals and the narration around them."""

    _buf: str = ""
    _mode: str = "text"  # text | html | style_wait | fence | table
    _block: list[str] = field(default_factory=list)
    _root: str = ""
    _depth: int = 0
    _fence: str = ""
    _fence_closed: bool = (
        False  # did the open fence get its closing line before the stream ended
    )
    _lang: str = ""
    _held: Visual | None = None  # html visual waiting to see if a <style> follows

    def feed(self, chunk: str) -> Iterator[SegmentPiece]:
        """Take the next slice of the stream and return whatever segments it completed."""
        self._buf += chunk
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            yield from self._line(line + "\n")

    def finish(self) -> Iterator[SegmentPiece]:
        """Flush whatever is left when the stream ends."""
        if self._buf:
            line, self._buf = self._buf, ""
            yield from self._line(line)
        if self._mode == "table":
            yield self._flush_block("table")
        elif self._mode in ("html", "fence"):  # unterminated: emit what we have
            kind = "html" if self._mode == "html" else self._fence_kind()
            yield self._flush_block(kind)
        elif (
            self._mode == "style"
        ):  # unterminated <style>: attach what we have to the visual
            yield from self._close_style()
        if self._held is not None:
            held, self._held = self._held, None
            yield held
        self._mode = "text"

    # -- per line -------------------------------------------------------------------------

    def _line(self, line: str) -> Iterator[SegmentPiece]:
        if self._mode == "html":
            self._block.append(line)
            self._depth += _tag_delta(line, self._root)
            if self._depth <= 0:
                self._held = self._flush_block("html")
                self._mode = "style_wait"
            return
        if self._mode == "style_wait":
            if not line.strip():
                return  # blank lines between the block and a possible <style>
            if _STYLE_OPEN.match(line):
                self._mode = "style"
                self._block = [line]
                if _STYLE_CLOSE.search(line):
                    yield from self._close_style()
                return
            held, self._held = self._held, None
            if held is not None:
                yield held
            self._mode = "text"
            yield from self._line(line)
            return
        if self._mode == "style":
            self._block.append(line)
            if _STYLE_CLOSE.search(line):
                yield from self._close_style()
            return
        if self._mode == "fence":
            if _closes_fence(line, self._fence):
                self._block.append(line)
                self._fence_closed = True
                yield self._flush_block(self._fence_kind())
                self._mode = "text"
            else:
                self._block.append(line)
            return
        if self._mode == "table":
            if _TABLE_LINE.match(line):
                self._block.append(line)
                return
            yield self._flush_block("table")
            self._mode = "text"
            yield from self._line(line)
            return

        # text mode: does this line open something?
        m = _FENCE_OPEN.match(line.rstrip("\n"))
        if m:
            self._mode, self._fence, self._lang = (
                "fence",
                m.group(1),
                m.group(2).lower(),
            )
            self._block = [line]
            self._fence_closed = False
            return
        m = _HTML_OPEN.match(line)
        if m:
            self._root = m.group(1).lower()
            self._block = [line]
            self._depth = _tag_delta(line, self._root)
            if self._depth <= 0:
                self._held = self._flush_block("html")
                self._mode = "style_wait"
            else:
                self._mode = "html"
            return
        if _IMAGE_LINE.match(line):
            yield Visual(kind="image", content=line.strip())
            return
        if _TABLE_LINE.match(line):
            self._mode = "table"
            self._block = [line]
            return
        # narration goes out clean: TTS and captions must not read markdown markers
        yield Narration(text=plain_narration(line) if line.strip() else line)

    def _close_style(self) -> Iterator[SegmentPiece]:
        """Attach a closed <style>/<script> block to the held visual and keep waiting for more."""
        style = "".join(self._block)
        self._block = []
        base = self._held.content if self._held is not None else ""
        self._held = Visual(kind="html", content=base + style)
        self._mode = "style_wait"
        return
        yield  # pragma: no cover - keeps this a generator

    def _fence_kind(self) -> str:
        return {"html": "html", "svg": "svg", "mermaid": "mermaid"}.get(
            self._lang, "code"
        )

    def _flush_block(self, kind: str) -> Visual:
        content = "".join(self._block)
        self._block = []
        if kind == "code":
            return Visual(kind="code", content=content, language=self._lang or None)
        if kind in ("html", "svg", "mermaid") and content.lstrip().startswith(
            ("```", "~~~")
        ):
            # Strip the fence so hosts get renderable markup. An unterminated fence -- the stream
            # ended mid-block -- has no closing line, so dropping its last line would throw away
            # real content and leave a one-line visual empty.
            lines = content.splitlines(keepends=True)
            end = -1 if self._fence_closed else len(lines)
            content = "".join(lines[1:end]) if len(lines) >= 2 else content
        return Visual(kind=kind, content=content)  # type: ignore[arg-type]
