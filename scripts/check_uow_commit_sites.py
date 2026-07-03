#!/usr/bin/env python3
"""Ratchet check: no new ``db.session.commit()`` outside the dao layer.

The backend overhaul (docs/exec-plans/active/backend-overhaul-master.md, B4)
migrates service code to the unit-of-work boundary in ``flaskr/dao/uow.py``.
Legacy commit call sites are grandfathered in a committed baseline; this check
fails when a file GAINS commit calls versus that baseline, and asks you to
shrink the baseline when a file drops calls, so the count only ratchets down.

Usage:
    python scripts/check_uow_commit_sites.py            # verify
    python scripts/check_uow_commit_sites.py --update   # rewrite the baseline
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "src" / "api" / "flaskr"
BASELINE_PATH = REPO_ROOT / "docs" / "generated" / "uow-commit-baseline.json"
COMMIT_RE = re.compile(r"\bdb\.session\.commit\(\)")

# The dao layer owns transaction control; tests manage their own sessions.
ALLOWED_PREFIXES = ("dao/",)


def scan() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        n = len(COMMIT_RE.findall(path.read_text(encoding="utf-8")))
        if n:
            counts[rel] = n
    return counts


def main() -> int:
    current = scan()
    if "--update" in sys.argv:
        BASELINE_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Baseline updated: {BASELINE_PATH} ({sum(current.values())} sites)")
        return 0

    if not BASELINE_PATH.exists():
        print(f"Missing baseline {BASELINE_PATH}; run with --update to create it.")
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    regressions = {
        rel: (baseline.get(rel, 0), n)
        for rel, n in current.items()
        if n > baseline.get(rel, 0)
    }
    improvements = {
        rel: (baseline.get(rel, 0), current.get(rel, 0))
        for rel in baseline
        if current.get(rel, 0) < baseline[rel]
    }

    if regressions:
        print("New db.session.commit() call sites outside flaskr/dao/:")
        for rel, (old, new) in sorted(regressions.items()):
            print(f" - flaskr/{rel}: {old} -> {new}")
        print(
            "Use `with unit_of_work():` from flaskr/dao/uow.py instead of "
            "committing directly (see backend-overhaul-master.md B4). If a "
            "direct commit is genuinely required, update the baseline with "
            "`python scripts/check_uow_commit_sites.py --update` and justify "
            "it in the PR."
        )
        return 1

    if improvements:
        print(
            "Commit sites decreased in: "
            + ", ".join(f"flaskr/{rel}" for rel in sorted(improvements))
            + ". Run `python scripts/check_uow_commit_sites.py --update` to "
            "ratchet the baseline down."
        )
        return 1

    print(f"uow commit-site ratchet OK ({sum(current.values())} grandfathered sites).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
