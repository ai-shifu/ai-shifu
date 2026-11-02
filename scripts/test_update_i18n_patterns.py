# ruff: noqa: INP001 -- These tests exercise a standalone repository script.
"""Verify dotted translation-key extraction handles near misses safely."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import update_i18n


class FrontendTranslationPatternTest(unittest.TestCase):
    """Preserve key extraction without nested ambiguous repetitions."""

    def test_dotted_keys_and_existing_permissive_character_rules(self) -> None:
        for key in ("module.key", "a.b.c", "a..b", "...", ".a.b.", "a_.b-0"):
            with self.subTest(key=key):
                assert update_i18n._find_frontend_keys(f"t('{key}')") == {key}

    def test_missing_dots_and_unterminated_calls_do_not_match(self) -> None:
        for source in ("t('plain')", "t('.a')", "t('a.')", "t('a.b'", "t('a.b)"):
            with self.subTest(source=source):
                assert update_i18n._find_frontend_keys(source) == set()

    def test_nested_calls_and_trailing_arguments_keep_existing_nonoverlap(
        self,
    ) -> None:
        for source, expected in (
            (
                "t('first.key', {count: 2}); t('second.key')",
                {"first.key", "second.key"},
            ),
            ("t('outer.key', t('inner.key'))", {"outer.key"}),
            ("t('plain', t('inner.key'))", {"inner.key"}),
            ("t('first.key') + t('unfinished.key'", {"first.key"}),
        ):
            with self.subTest(source=source):
                assert update_i18n._find_frontend_keys(source) == expected

    def test_incomplete_key_with_many_dots_finishes_within_process_deadline(
        self,
    ) -> None:
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import update_i18n; "
                "source = \"t('\" + '-.' * 100000; "
                "assert update_i18n._find_frontend_keys(source) == set()",
            ],
            cwd=Path(__file__).resolve().parent,
            check=True,
            timeout=20,
        )

    def test_repeated_unclosed_calls_finish_within_process_deadline(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import update_i18n; "
                "source = \"t('a.b'\" * 200000; "
                "assert update_i18n._find_frontend_keys(source) == set()",
            ],
            cwd=Path(__file__).resolve().parent,
            check=True,
            timeout=20,
        )


if __name__ == "__main__":
    unittest.main()
