"""Verify the ANN201 public-return annotation policy boundaries."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MISSING_RETURN_ANNOTATION_SOURCE = '''"""Fixture module used to verify the ANN201 policy."""
# ruff: noqa: INP001


def public_function():
    return None
'''
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
    "src/api/flaskr/service/profile/profile_manage.py": {
        "save_profile_item": "ProfileItemDefinition",
        "delete_profile_item": "bool",
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
    "src/api/flaskr/util/datetime.py": {"get_now_time": "datetime"},
    "src/api/migrations/env.py": {"include_object": "bool"},
    "src/api/scripts/inventory/match_routes.py": {"grep_paths": "set[tuple[str, ...]]"},
}


class RuffAnn201PolicyTest(unittest.TestCase):
    """Protect ANN201 enforcement while retaining immutable migration history."""

    @classmethod
    def setUpClass(cls) -> None:
        """Resolve the same Ruff executable used by local and CI checks."""
        cls.ruff = os.environ.get("RUFF_BIN") or shutil.which("ruff")
        if cls.ruff is None:
            message = "ruff is not installed"
            raise unittest.SkipTest(message)

    def run_ruff(self, filename: str) -> subprocess.CompletedProcess[str]:
        """Run configured Ruff against fixture source at one repository path."""
        return subprocess.run(
            [
                self.ruff,
                "check",
                "--config",
                str(REPO_ROOT / "ruff.toml"),
                "--stdin-filename",
                filename,
                "-",
            ],
            cwd=REPO_ROOT,
            input=MISSING_RETURN_ANNOTATION_SOURCE,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_migration_history_remains_exempt(self) -> None:
        """Keep immutable Alembic revisions outside ANN201 enforcement."""
        result = self.run_ruff("src/api/migrations/versions/ann201_fixture.py")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "ANN201" not in result.stdout

    def test_production_function_requires_a_return_annotation(self) -> None:
        """Require an explicit return type for public production functions."""
        result = self.run_ruff("src/api/flaskr/ann201_fixture.py")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "ANN201" in result.stdout

    def test_reviewed_functions_keep_their_concrete_return_contracts(self) -> None:
        """Keep reviewed ANN201 annotations narrower than ``object``."""
        for relative_path, expected_returns in REVIEWED_RETURN_CONTRACTS.items():
            with self.subTest(relative_path=relative_path):
                source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
                functions = {
                    node.name: node
                    for node in ast.walk(ast.parse(source))
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                for function_name, expected_return in expected_returns.items():
                    with self.subTest(function_name=function_name):
                        actual_return = ast.unparse(functions[function_name].returns)
                        assert actual_return == expected_return
