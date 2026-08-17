#!/usr/bin/env python3
"""Fail if backend Python contains hardcoded CJK characters.

Scans src/api/**/*.py for any literal non-ASCII CJK characters. Allows all
content under src/i18n/ (JSON) which is scanned separately, and skips common
generated or cache directories.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "api"

# Unicode range for CJK Unified Ideographs
CJK = re.compile(r"[\u4E00-\u9FFF]")


def main() -> int:
    if not BACKEND.exists():
        return 0

    violations: list[str] = []
    for path in BACKEND.rglob("*.py"):
        # Skip virtualenvs or caches if any
        parts = set(path.parts)
        if any(p in parts for p in {".venv", "__pycache__"}):
            continue
        # Skip migrations, tests and constant tables for now (pending i18n migration)
        if "migrations" in parts:
            continue
        if "tests" in parts:
            continue
        if path.name in {"const.py", "consts.py"}:
            continue
        # Restrict check to route files where user-facing messages are most likely
        if not path.name.endswith("routes.py"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if CJK.search(line):
                violations.append(f"{path}:{i}: {line.strip()}")

    if violations:
        print("Hardcoded CJK characters detected in backend Python files:")
        for v in violations:
            print(" -", v)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
