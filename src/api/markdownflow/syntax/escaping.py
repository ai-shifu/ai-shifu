r"""Backslash escapes for the delimiters inside an interaction's brackets.

`?[A|B]` gives `|`, `//`, `...` and `]` structural meaning, so option text that contains one of
them is reshaped: a bar splits one choice into two, a double slash gives half the display away to
the stored value, an ellipsis turns the rest into a text box, and a bracket ends the interaction
early. An option carrying a URL or a regular expression could not be written at all.

A backslash before one of those characters now makes it ordinary text.

The escape is deliberately *selective*: a backslash is an escape only when the character after it
is a delimiter, and is literal text everywhere else. `\\\\` is not an escape either. That matters
for content that already exists: of 110,685 interactions in published courses, 97 contain a
backslash and every one of them is LaTeX -- `$\\pi_\\theta$`, `\\beta`, `\\nabla`, and `\\\\` as a
line break. A general "backslash escapes the next character" rule would render those as
`$pi_theta$`. Under this rule, none of them change.

The cost is that a literal backslash cannot sit immediately before a literal delimiter: `\\|` is
an escaped bar, not a backslash and a separator. Nothing in the measured corpus writes that.
"""

from .variable_names import read_variable_marker

# The characters a backslash may make ordinary. `/` covers `//`, `.` covers `...`.
ESCAPABLE = "|/.]"


def is_escape(text: str, index: int) -> bool:
    """Whether the backslash at `index` escapes the character after it."""
    return (
        index + 1 < len(text) and text[index] == "\\" and text[index + 1] in ESCAPABLE
    )


def escape_interaction_text(text: str) -> str:
    r"""Make `text` safe to write inside `?[...]`, keeping every character it has.

    A dot is escaped only inside a run of three or more, because only `...` is a delimiter and a
    single period ends most sentences: escaping every one turns `Yes, I agree.` into
    `Yes, I agree\\.` in everything that stores or shows the raw interaction. Two dots cannot
    become three on their own, and the run is escaped whole so it cannot be read as one.

    Bars, brackets and slashes are escaped wherever they appear. They are rare in option text,
    and escaping them unconditionally removes the need to reason about what a neighbouring
    character might combine with once the option is written next to a separator.

    Escaping the delimiters rather than the backslashes as well is what keeps existing content
    readable: a script that writes `$\\pi$` in an option still writes `$\\pi$` afterwards.
    """
    out: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            marker = read_variable_marker(text, index)
            end = marker.end if marker is not None else len(text)
            out.append(text[index:end])
            index = end
            continue
        char = text[index]
        if char == ".":
            run = len(text) - index - len(text[index:].lstrip("."))
            # A run of three or more is the `...` delimiter. A shorter one still needs escaping
            # when a literal backslash precedes it, because the parser would read that backslash
            # and the dot as an escape pair and drop the backslash -- `a\\.b` would come back as
            # `a.b`, the round trip would fail, and the question would be refused. Escaping the
            # dot puts a second backslash in front of it, which the parser reads as one literal
            # backslash followed by an escaped dot: exactly the text that went in.
            if run >= 3 or (index > 0 and text[index - 1] == "\\"):
                out.append("\\." * run)
            else:
                out.append("." * run)
            index += run
            continue
        if char in ESCAPABLE:
            out.append("\\")
        out.append(char)
        index += 1
    return "".join(out)


def unescape_interaction_text(text: str) -> str:
    """Resolve the escapes in one option's text, leaving every other backslash alone."""
    out: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            marker = read_variable_marker(text, index)
            end = marker.end if marker is not None else len(text)
            out.append(text[index:end])
            index = end
            continue
        if is_escape(text, index):
            out.append(text[index + 1])
            index += 2
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def find_unescaped(text: str, needle: str, start: int = 0) -> int:
    """Index of the first `needle` that is not escaped and does not begin inside an escape.

    Returns -1 when there is none. `needle` is matched whole: a `//` whose first slash is escaped
    is not a separator even though its second slash is bare, because that second slash is the
    escaped character of the pair.
    """
    index = start
    while index < len(text):
        if text.startswith("{{", index):
            marker = read_variable_marker(text, index)
            if marker is None:
                return -1
            index = marker.end
            continue
        if is_escape(text, index):
            index += 2
            continue
        if text.startswith(needle, index):
            return index
        index += 1
    return -1


def split_unescaped(text: str, separator: str) -> list[str]:
    """Split on every unescaped `separator`, leaving the escapes themselves in place."""
    parts: list[str] = []
    start = 0
    while True:
        found = find_unescaped(text, separator, start)
        if found < 0:
            parts.append(text[start:])
            return parts
        parts.append(text[start:found])
        start = found + len(separator)


def split_on_single_pipe(text: str) -> list[str]:
    """Split on unescaped single bars, leaving `||` joined as the multi-select separator."""
    parts: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if text.startswith("{{", index):
            marker = read_variable_marker(text, index)
            index = marker.end if marker is not None else len(text)
            continue
        if is_escape(text, index):
            index += 2
            continue
        if text[index] == "|":
            if text.startswith("||", index):
                index += 2
                continue
            if index > 0 and text[index - 1] == "|" and not is_escape(text, index - 1):
                index += 1
                continue
            parts.append(text[start:index])
            start = index + 1
        index += 1
    parts.append(text[start:])
    return parts


def rfind_unescaped(text: str, needle: str) -> int:
    """Index of the *last* unescaped `needle`, or -1."""
    found = -1
    start = 0
    while True:
        at = find_unescaped(text, needle, start)
        if at < 0:
            return found
        found = at
        start = at + 1


def split_on_ellipsis(content: str) -> tuple[str, str] | None:
    r"""Split an interaction's content at the `...` that opens its text box, or None.

    Two details are inherited rather than chosen, because changing either would rewrite questions
    in courses that are already published:

    * the ellipsis counts only on the first line. The regex this replaces was anchored and its
      `.` did not cross a newline, so `A\n| ...hint` has always been read as two buttons, one of
      them named `...hint`. 122 published interactions depend on that reading.
    * the *last* ellipsis on that line wins, which is what the greedy group matched.

    What is new is only that an escaped ellipsis no longer counts.
    """
    newline = find_unescaped(content, "\n")
    head = content[:newline] if newline >= 0 else content
    at = rfind_unescaped(head, "...")
    if at < 0:
        return None
    return head[:at], head[at + 3 :]
