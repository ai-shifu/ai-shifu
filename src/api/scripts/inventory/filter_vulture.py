#!/usr/bin/env python3
"""Post-process vulture output, excluding known false-positive classes:
- functions decorated with @inject or Flask route decorators (@*.route(...))
- functions named register_* (route registration entry points)
- __json__ methods
- celery @shared_task functions
- anything under migrations/
Usage: filter_vulture.py <vulture-raw.txt> <src_api_root>
"""

import re
import sys
import os
from collections import Counter

RAW, ROOT = sys.argv[1], sys.argv[2]

LINE_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+): (?P<msg>unused \w+ '(?P<sym>[^']+)'.*)\((?P<conf>\d+)% confidence\)"
)

file_cache = {}


def get_lines(path):
    if path not in file_cache:
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                file_cache[path] = f.readlines()
        except OSError:
            file_cache[path] = []
    return file_cache[path]


def decorators_above(path, lineno):
    """Collect decorator text for the flagged symbol.

    Vulture flags the FIRST decorator's line for decorated defs, so scan
    from the flagged line down to the def/class line (grabbing the whole
    decorator block, including multi-line calls), and also scan upward in
    case the flagged line is the def itself.
    """
    lines = get_lines(path)
    decs = []
    # downward: flagged line may be the first decorator
    i = lineno - 1  # 0-based flagged line
    limit = min(len(lines), i + 40)
    while i < limit:
        stripped = lines[i].strip()
        if stripped.startswith(("def ", "class ", "async def ")):
            break
        decs.append(stripped)
        i += 1
    return decs


kept, excluded = [], []
with open(RAW, encoding="utf-8") as f:
    for raw_line in f:
        raw_line = raw_line.rstrip("\n")
        m = LINE_RE.match(raw_line)
        if not m:
            continue
        path, lineno, sym, conf, msg = (
            m["file"],
            int(m["line"]),
            m["sym"],
            int(m["conf"]),
            m["msg"],
        )
        reason = None
        if "/migrations/" in path or path.startswith("migrations/"):
            reason = "migrations"
        elif sym == "__json__":
            reason = "__json__ reflection serializer"
        elif sym.startswith("register_"):
            reason = "register_* route registration"
        elif (
            "unused function" in msg or "unused method" in msg or "unused class" in msg
        ):
            decs = decorators_above(path, lineno)
            joined = " ".join(decs)
            if "@inject" in joined:
                reason = "@inject plugin-loaded"
            elif ".route(" in joined or "@app.route" in joined:
                reason = "flask route decorator"
            elif "shared_task" in joined:
                reason = "celery shared_task"
        if reason:
            excluded.append((raw_line, reason))
        else:
            kept.append((path, lineno, sym, conf, msg))

print(f"# kept={len(kept)} excluded={len(excluded)}")
print("\n## KEPT FINDINGS (file:line | symbol | confidence | message)")
for path, lineno, sym, conf, msg in kept:
    print(f"{path}:{lineno} | {sym} | {conf}% | {msg.strip()}")
print("\n## EXCLUDED (false-positive classes)")
c = Counter(r for _, r in excluded)
for r, n in c.most_common():
    print(f"- {r}: {n}")
for line, r in excluded:
    print(f"[{r}] {line}")
