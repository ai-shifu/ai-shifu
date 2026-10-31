"""Formatter Regex Patterns.

Pre-compiled regular expressions for line-level content detection.
Mirrors Go formatter/patterns.go.
"""

import re

# === Inherited from splitter/patterns.go ===

# SVG open tag <svg or <svg>
svg_open_re = re.compile(r"(?i)<svg[\s>]")
# SVG close tag </svg>
svg_close_re = re.compile(r"(?i)</svg>")

# Block-level HTML open tags
block_html_open_re = re.compile(
    r"(?i)^\s*<(div|style|script|iframe|section|article|header|footer|nav|main|aside|"
    r"figure|details|summary|form|table|canvas|video|audio|pre|blockquote|ul|ol|dl|"
    r"fieldset|address|hgroup|center)[\s>/]"
)

# </style> close
style_close_re = re.compile(r"(?i)</style>")

# </script> close
script_close_re = re.compile(r"(?i)</script>")

# <!DOCTYPE html> declaration
doctype_re = re.compile(r"(?i)^\s*<!DOCTYPE\s+html")
# </html> close
html_close_re = re.compile(r"(?i)</html>")

# Markdown table row: | ... | or | --- | --- |
table_row_re = re.compile(r"^\s*\|.*\|\s*$")

# Standalone markdown image line: ![alt](url)
image_line_re = re.compile(r"^\s*!\[([^\]]*)\]\(([^)]+)\)\s*$")

# HTML open tag name extraction (for nesting depth tracking)
html_open_tag_re = re.compile(
    r"(?i)<(div|style|script|iframe|section|article|header|footer|nav|main|aside|"
    r"figure|details|summary|form|table|canvas|video|audio|pre|blockquote|ul|ol|dl|"
    r"fieldset|address|hgroup|center)[\s>/]"
)
# HTML close tag name extraction (for nesting depth tracking)
html_close_tag_re = re.compile(
    r"(?i)</(div|style|script|iframe|section|article|header|footer|nav|main|aside|"
    r"figure|details|summary|form|table|canvas|video|audio|pre|blockquote|ul|ol|dl|"
    r"fieldset|address|hgroup|center)>"
)

# === Formatter-specific patterns ===

# Diff fence marker !+++
diff_fence_re = re.compile(r"^\s*!\+\+\+\s*$")

# LaTeX display math standalone line $$
display_math_re = re.compile(r"^\s*\$\$\s*$")

# Standalone inline LaTeX $...$
inline_math_line_re = re.compile(r"^\s*\$[^$]+\$\s*$")

# Markdown heading # to ######
heading_re = re.compile(r"^\s{0,3}#{1,6}\s")

# HTML <img> tag
html_img_re = re.compile(r"(?i)^\s*<img\s")

# HTML <link> tag (void element, typically CSS include)
html_link_re = re.compile(r"(?i)^\s*<link\s")
