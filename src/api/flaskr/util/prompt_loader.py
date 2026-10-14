"""Provide prompt loader utilities."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from markdown_it import MarkdownIt
from markdown_it.rules_inline import html_inline

if TYPE_CHECKING:
    from markdown_it.rules_inline.state_inline import StateInline


def strip_html_comments(text: str, *, preserve_offsets: bool = False) -> str:
    """Remove authored notes before substitution, preserving Markdown code examples.

    Parse a marked copy: marker IDs identify original source positions without
    rebuilding Markdown from its tokens or matching repeated rendered content.
    MarkdownIt handles code, escapes, links, and nested containers; HTMLParser
    distinguishes comments from quoted attributes inside raw HTML blocks.
    An unfinished note outside code ends at the source document boundary.
    """
    starts = [match.start() for match in re.finditer("<!--", text)]
    if not starts:
        return text
    prefix = f"MDFCOMMENT_{uuid4().hex}_"
    while prefix in text:
        prefix = f"MDFCOMMENT_{uuid4().hex}_"
    marker = re.compile(re.escape(prefix) + r"(\d+)__")
    marked: list[str] = []
    cursor = 0
    for index, start in enumerate(starts):
        marked.append(text[cursor:start])
        identifier = f"{prefix}{index}__"
        # CommonMark accepts both short empty-comment spellings. Inserting an
        # ID into either opener alone would turn the copy into an unclosed note.
        short = (
            5
            if text.startswith("<!-->", start)
            else 6
            if text.startswith("<!--->", start)
            else 0
        )
        marked.append(f"<!--{identifier}-->" if short else f"<!--{identifier}")
        cursor = start + (short or 4)
    marked.append(text[cursor:])
    found: set[int] = set()

    def capture(content: str) -> None:
        found.update(int(match[1]) for match in marker.finditer(content))

    def authored_comment(state: StateInline, silent: bool) -> bool:
        start = state.pos
        if html_inline(state, silent):
            if not silent and state.src.startswith("<!--", start):
                capture(state.src[start : state.pos])
            return True
        # CommonMark leaves unfinished inline comments as text. Author notes
        # have the stricter product rule documented above, after code/escaping
        # and valid HTML attributes have already been handled by native rules.
        opening = (
            marker.match(state.src, start + 4)
            if state.src.startswith("<!--", start)
            else None
        )
        if opening is None or silent:
            return False
        found.add(int(opening[1]))
        closing = state.src.find("-->", start + 4)
        state.pos = closing + 3 if closing >= 0 else state.posMax
        return True

    class Comments(HTMLParser):
        def handle_comment(self, data: str) -> None:
            capture(data)

    parser = MarkdownIt("commonmark")
    parser.inline.ruler.at("html_inline", authored_comment)
    for token in parser.parse("".join(marked)):
        if token.type == "html_block":
            reader = Comments(convert_charrefs=False)
            reader.feed(token.content)
            if reader.rawdata.startswith(f"<!--{prefix}"):
                capture(reader.rawdata)

    parts: list[str] = []
    cursor = 0
    for index, start in enumerate(starts):
        if index not in found or start < cursor:
            continue
        parts.append(text[cursor:start])
        if text.startswith("<!-->", start):
            end = start + 5
        elif text.startswith("<!--->", start):
            end = start + 6
        else:
            closing = text.find("-->", start + 4)
            end = closing + 3 if closing >= 0 else len(text)
        if preserve_offsets:
            parts.append(
                "".join(char if char in "\r\n" else " " for char in text[start:end])
            )
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def load_prompt_template(template_name: str) -> str:
    """Load the specified prompt template file.

    Args:
        template_name: Template file name (without .md extension)

    Returns:
        Template file content

    Raises:
        FileNotFoundError: When template file does not exist

    """
    # Get the directory of current file
    current_dir = str(Path(__file__).resolve().parent)
    # Build prompts directory path
    prompts_dir = str(Path(current_dir) / "../../prompts")

    # Ensure filename has .md extension
    if not template_name.endswith(".md"):
        template_name = f"{template_name}.md"

    # Build complete file path
    template_path = str(Path(prompts_dir) / template_name)

    # Check if file exists
    if not Path(template_path).exists():
        message = f"Prompt template file not found: {template_path}"
        raise FileNotFoundError(message)

    # Read file content
    try:
        with Path(template_path).open(encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        message = f"Failed to read prompt template file {template_path}: {e!s}"
        raise OSError(message) from e
