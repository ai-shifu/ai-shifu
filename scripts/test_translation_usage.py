#!/usr/bin/env python3
"""Regression tests for runtime translation usage validation."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_translation_usage as usage


class TranslationUsageTest(unittest.TestCase):
    """Exercise the checker against a small repository fixture."""

    def setUp(self) -> None:
        self.tempdir = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.tempdir)
        self.web = self.root / "src/web/src"
        self.backend = self.root / "src/api"
        self.i18n = self.root / "src/i18n"
        self.web.mkdir(parents=True)
        self.backend.mkdir(parents=True)
        (self.i18n / "en-US").mkdir(parents=True)
        for name, value in (
            ("ROOT", self.root),
            ("WEB_DIR", self.web),
            ("BACKEND_DIR", self.backend),
            ("I18N_DIR", self.i18n),
        ):
            self.enterContext(patch.object(usage, name, value))

    def define(self, namespace: str, values: dict[str, str]) -> None:
        path = self.i18n / "en-US" / f"{namespace}.json"
        path.write_text(json.dumps({"__namespace__": namespace, "__flat__": values}))
        namespaces = sorted(
            json.loads(p.read_text())["__namespace__"]
            for p in (self.i18n / "en-US").glob("*.json")
        )
        (self.i18n / "locales.json").write_text(json.dumps({"namespaces": namespaces}))

    def run_check(self) -> tuple[int, str]:
        output = io.StringIO()
        with (
            patch("sys.argv", ["check_translation_usage.py", "--fail-on-unused"]),
            contextlib.redirect_stdout(output),
        ):
            status = usage.main()
        return status, output.getvalue()

    def test_generated_declarations_and_tests_do_not_hide_unused_keys(self) -> None:
        self.define("module.example", {"retired": "Retired"})
        (self.web / "keys.d.ts").write_text(
            "export type Key = 'module.example.retired';"
        )
        for name in ("page.test.ts", "page.spec.ts", "helpers.test-support.ts"):
            (self.web / name).write_text("t('module.example.retired');")
        tests = self.backend / "tests"
        tests.mkdir()
        (tests / "test_profile.py").write_text("_('module.example.retired')")
        status, output = self.run_check()
        assert status == 1
        assert "Unused translation keys" in output
        assert "module.example.retired" in output

    def test_key_constants_survive_apostrophes_and_nested_templates(self) -> None:
        self.define("module.example", {"save": "Save", "cancel": "Cancel"})
        (self.web / "page.tsx").write_text(
            "// The user's choice is preserved.\n"
            "const key = 'module.example.save';\n"
            "const label = `${t('module.example.cancel')}`;\n"
            "translateRef.current(key);"
        )
        assert self.run_check()[0] == 0

    def test_dynamic_templates_preserve_only_matching_families(self) -> None:
        self.define(
            "module.example",
            {"status.ready": "Ready", "status.failed": "Failed", "retired": "Old"},
        )
        (self.web / "page.tsx").write_text("t(`module.example.status.${status}`);")
        status, output = self.run_check()
        assert status == 1
        assert " - module.example.retired" in output
        assert " - module.example.status." not in output

    def test_namespaced_and_forwarded_relative_translators(self) -> None:
        self.define("module.example", {"save": "Save", "dialog.title": "Title"})
        (self.web / "page.tsx").write_text(
            "const { t: translate } = useTranslation('module.example');\n"
            "translate('save');"
        )
        (self.web / "dialog.tsx").write_text("props.translate('dialog.title');")
        assert self.run_check()[0] == 0

    def test_relative_dynamic_template_with_an_infix_enum(self) -> None:
        self.define(
            "module.example",
            {"contact.emailRequired": "Email", "contact.phoneRequired": "Phone"},
        )
        (self.web / "page.tsx").write_text(
            "const { t } = useTranslation('module.example');\n"
            "t(`contact.${kind}Required`);"
        )
        assert self.run_check()[0] == 0

    def test_backend_constants_and_dynamic_error_keys(self) -> None:
        self.define(
            "server.user",
            {"emailUnchanged": "Email", "phoneUnchanged": "Phone", "busy": "Busy"},
        )
        (self.backend / "service.py").write_text(
            'BUSY = "server.user.busy"\n'
            "raise_error(BUSY)\n"
            'raise_error(f"server.user.{contact_type}Unchanged")\n'
        )
        assert self.run_check()[0] == 0

    def test_frontend_legacy_aliases_keep_canonical_backend_keys(self) -> None:
        self.define("server.common", {"operationFailed": "Failed"})
        self.define("server.shifu", {"courseNotFound": "Missing"})
        self.define("server.outline", {"lessonNotFound": "Missing"})
        (self.web / "page.tsx").write_text(
            "t('module.backend.common.operationFailed');\n"
            "t('module.backend.course.courseNotFound');\n"
            "t('module.backend.lesson.lessonNotFound');"
        )
        assert self.run_check()[0] == 0

    def test_missing_literal_key_still_fails(self) -> None:
        self.define("module.example", {"save": "Save"})
        (self.web / "page.tsx").write_text(
            "t('module.example.save'); t('module.example.missing');"
        )
        status, output = self.run_check()
        assert status == 1
        assert "Missing translation keys" in output
        assert "module.example.missing" in output

    def test_shared_component_constants_and_bare_words(self) -> None:
        self.define("component.example", {"save": "Save", "retired": "Retired"})
        (self.web / "page.tsx").write_text(
            "const key = 'component.example.save'; const action = 'retired';"
        )
        status, output = self.run_check()
        assert status == 1
        assert " - component.example.retired" in output
        assert " - component.example.save" not in output


if __name__ == "__main__":
    unittest.main()
