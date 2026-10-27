"""Read the prompt resources shipped with the independent engine library."""

from __future__ import annotations

import re
from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return a bundled prompt's exact text by its name without the .md suffix."""
    if re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
        message = "prompt name must be a lowercase identifier without a file suffix"
        raise ValueError(message)
    return (
        files("markdownflow.engine")
        .joinpath("prompts", f"{name}.md")
        .read_text(encoding="utf-8")
    )
