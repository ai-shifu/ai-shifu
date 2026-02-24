"""
Centralized regex patterns for TTS text processing and AV segmentation.

All compiled regex patterns used across the TTS service layer are defined
here. Import patterns from this module rather than defining them locally.
"""

import re

# ---------------------------------------------------------------------------
# Markdown text cleaning (used by preprocess_for_tts)
# ---------------------------------------------------------------------------
CODE_BLOCK = re.compile(r"```[\s\S]*?```|`[^`]+`")
HEADER = re.compile(r"^#+\s+", re.MULTILINE)
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]+\)")
BOLD_ITALIC = re.compile(r"\*{1,3}([^*]+)\*{1,3}|_{1,3}([^_]+)_{1,3}")
LIST_MARKER = re.compile(r"^[\s]*[-*+]\s+|^[\s]*\d+\.\s+", re.MULTILINE)
MERMAID_BLOCK = re.compile(r"```mermaid[\s\S]*?```")
SVG_BLOCK = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)
XML_BLOCK = re.compile(r"<(svg|math|script|style)[^>]*>[\s\S]*?</\1>", re.IGNORECASE)
DATA_URI = re.compile(r"data:[a-zA-Z0-9/+;=,]+")
MULTI_NEWLINE = re.compile(r"\n{3,}")
MULTI_SPACE = re.compile(r"[ \t]+")
ANY_HTML_TAG = re.compile(r"<[^>]*>")

# Stray SVG text elements (malformed streaming fragments)
SVG_TEXT_TAGS = [
    re.compile(rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>", re.IGNORECASE)
    for tag in ("text", "tspan", "title", "desc")
]

# ---------------------------------------------------------------------------
# AV segmentation — visual boundary detection (pipeline + streaming_tts)
# ---------------------------------------------------------------------------
# Open patterns
AV_SVG_OPEN = re.compile(r"<svg\b", re.IGNORECASE)
AV_IFRAME_OPEN = re.compile(r"<iframe\b", re.IGNORECASE)
AV_VIDEO_OPEN = re.compile(r"<video\b", re.IGNORECASE)
AV_TABLE_OPEN = re.compile(r"<table\b", re.IGNORECASE)
AV_IMG_TAG = re.compile(r"<img\b[^>]*?>", re.IGNORECASE)

# Close patterns
AV_SVG_CLOSE = re.compile(r"</svg>", re.IGNORECASE)
AV_IFRAME_CLOSE = re.compile(r"</iframe>", re.IGNORECASE)
AV_VIDEO_CLOSE = re.compile(r"</video>", re.IGNORECASE)
AV_TABLE_CLOSE = re.compile(r"</table>", re.IGNORECASE)

# Markdown visual elements
AV_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^\)\n]*\)", re.IGNORECASE)
AV_MD_IMAGE_START = re.compile(r"!\[")
AV_MD_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)

# Sandbox / HTML block detection
AV_SANDBOX_START = re.compile(
    r"<(script|style|link|iframe|html|head|body|meta|title|base"
    r"|template|div|section|article|main)(?:[\s>/]|$)",
    re.IGNORECASE,
)
AV_CLOSING_BOUNDARY = re.compile(r"</[a-z][^>]*>\s*\n(?=[^\s<])", re.IGNORECASE)
AV_SPEAKABLE_HINT = re.compile(r"<(p|li|h[1-6])\b", re.IGNORECASE)

# Fixed marker validation
FIXED_MARKER_TAIL = re.compile(r"^[\s!=]*$")

# ---------------------------------------------------------------------------
# Streaming TTS
# ---------------------------------------------------------------------------
SENTENCE_ENDINGS = re.compile(r"[.!?。！？；;]")

# ---------------------------------------------------------------------------
# HTML tag extraction helpers
# ---------------------------------------------------------------------------
TAG_NAME_EXTRACT = re.compile(r"<([a-z0-9-]+)\b", re.IGNORECASE)
