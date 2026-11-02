#!/usr/bin/env python3
"""Check that ruff.toml still enforces its rules where it should, and only there.

Each policy runs the configured Ruff on fixture source under a path that the
configuration must either flag or exempt, so a broadened ignore or a dropped
rule fails here instead of passing silently. It also keeps the reviewed ANN201
return annotations narrower than ``object``.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MISSING_RETURN_ANNOTATION = '''"""Fixture module used to verify the ANN201 policy."""
# ruff: noqa: INP001


def public_function():
    return None
'''
UNDOCUMENTED_FUNCTION = '''"""Fixture module used to verify the D103 policy."""


def public_function() -> None:
    return None
'''
CONFUSABLE_TEXT = '''"""Fixture module used to verify the RUF001 policy."""
# ruff: noqa: INP001
value = "\uff08"
'''

# (rule, fixture source, path, whether the rule must be reported there, and the
# exit status Ruff must return, or None where other rules may still fire)
POLICIES: tuple[tuple[str, str, str, bool, int | None], ...] = (
    # ANN201: immutable migration history stays exempt; production code is not.
    (
        "ANN201",
        MISSING_RETURN_ANNOTATION,
        "src/api/migrations/versions/fixture.py",
        False,
        0,
    ),
    ("ANN201", MISSING_RETURN_ANNOTATION, "src/api/flaskr/ann201_fixture.py", True, 1),
    # D103: exceptions are limited to tests, fixtures and migration history.
    ("D103", UNDOCUMENTED_FUNCTION, "src/api/tests/docstring_fixture.py", False, None),
    ("D103", UNDOCUMENTED_FUNCTION, "scripts/test_docstring_fixture.py", False, None),
    (
        "D103",
        UNDOCUMENTED_FUNCTION,
        "src/api/migrations/versions/fixture.py",
        False,
        None,
    ),
    (
        "D103",
        UNDOCUMENTED_FUNCTION,
        "scripts/testdata/architecture_boundaries/docstring_fixture.py",
        False,
        None,
    ),
    ("D103", UNDOCUMENTED_FUNCTION, "src/api/flaskr/documentation_fixture.py", True, 1),
    # RUF001: verbatim fixtures may use confusable text under test paths only.
    ("RUF001", CONFUSABLE_TEXT, "example/tests/fixture.py", False, 0),
    ("RUF001", CONFUSABLE_TEXT, "example/test_fixture.py", False, 0),
    ("RUF001", CONFUSABLE_TEXT, "example/fixture_test.py", False, 0),
    ("RUF001", CONFUSABLE_TEXT, "example/conftest.py", False, 0),
    ("RUF001", CONFUSABLE_TEXT, "src/api/flaskr/confusable_fixture.py", True, 1),
)
# Reviewed ANN201 annotations, kept narrower than ``object``.
REVIEWED_RETURN_CONTRACTS = {
    "src/api/flaskr/api/check/yidun.py": {"gen_signature": "str"},
    "src/api/flaskr/api/doc/feishu.py": {"send_notify": "dict[str, object] | None"},
    "src/api/flaskr/route/callback.py": {"register_callback_handler": "Flask"},
    "src/api/flaskr/route/order.py": {"register_order_handler": "Flask"},
    "src/api/flaskr/service/common/models.py": {
        "raise_param_error": "Never",
        "raise_error": "Never",
        "raise_error_with_args": "Never",
    },
    "src/api/flaskr/service/feedback/funs.py": {"submit_feedback": "int"},
    "src/api/flaskr/service/order/funs.py": {
        "sync_stripe_checkout_session": "dict[str, Any]",
        "success_buy_record": "AICourseBuyRecordDTO | None",
    },
    "src/api/flaskr/service/profile/funcs.py": {
        "update_user_profile_with_lable": "bool"
    },
    "src/api/flaskr/service/shifu/funcs.py": {
        "mark_favorite_shifu": "bool",
        "unmark_favorite_shifu": "bool",
        "mark_or_unmark_favorite_shifu": "bool",
    },
    "src/api/flaskr/service/shifu/shifu_outline_funcs.py": {
        "get_unit_by_id": "OutlineDto",
        "modify_unit": "OutlineDto",
    },
    "src/api/flaskr/service/shifu/shifu_publish_funcs.py": {
        "preview_shifu_draft": "str",
        "publish_shifu_draft": "str",
    },
    "src/api/migrations/env.py": {"include_object": "bool"},
    "src/api/scripts/inventory/match_routes.py": {"grep_paths": "set[tuple[str, ...]]"},
}


def _ruff() -> str:
    ruff = os.environ.get("RUFF_BIN") or shutil.which("ruff")
    if ruff is None:
        message = "ruff is not installed; install the pinned version first"
        raise SystemExit(message)
    return ruff


def check_policies(ruff: str) -> list[str]:
    """Return a message for every fixture whose diagnostics break its policy."""
    problems: list[str] = []
    for rule, source, path, reported, exit_code in POLICIES:
        result = subprocess.run(
            [
                ruff,
                "check",
                "--config",
                str(REPO_ROOT / "ruff.toml"),
                "--stdin-filename",
                path,
                "-",
            ],
            cwd=REPO_ROOT,
            input=source,
            capture_output=True,
            text=True,
            check=False,
        )
        found = rule in result.stdout
        clean = exit_code is None or result.returncode == exit_code
        if found != reported or not clean:
            expectation = "must report" if reported else "must not report"
            problems.append(
                f"{path}: ruff {expectation} {rule} "
                f"(exit {result.returncode})\n{result.stdout}{result.stderr}"
            )
    return problems


def check_return_contracts() -> list[str]:
    """Return a message for every reviewed return annotation that changed."""
    problems: list[str] = []
    for relative_path, expected_returns in REVIEWED_RETURN_CONTRACTS.items():
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        functions = {
            node.name: node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name, expected in expected_returns.items():
            function = functions.get(name)
            actual = (
                ast.unparse(function.returns)
                if function is not None and function.returns is not None
                else None
            )
            if actual != expected:
                problems.append(
                    f"{relative_path}: {name} returns {actual!r}, reviewed as {expected!r}"
                )
    return problems


def main() -> int:
    """Run every policy check and report all failures together."""
    problems = check_policies(_ruff()) + check_return_contracts()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print("Ruff policy checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
