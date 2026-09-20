#!/usr/bin/env python3
"""Protect committed knowledge indexes and optional local health snapshots."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import build_repo_knowledge_index as generator
import check_repo_harness as harness


class RepoKnowledgeIndexTest(unittest.TestCase):
    """Exercise real generation and validation against an isolated repository."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        original_root = generator.ROOT

        def rebase(path: Path) -> Path:
            return self.root / path.relative_to(original_root)

        for module, names in (
            (
                generator,
                (
                    "ROOT",
                    "DOCS_ROOT",
                    "BOUNDARY_BASELINE_PATH",
                    "HARNESS_HEALTH_PATH",
                    "GARDENING_SUMMARY_PATH",
                ),
            ),
            (
                harness,
                ("ROOT", "DOCS_ROOT", "BOUNDARY_BASELINE", "GARDENING_SUMMARY_PATH"),
            ),
        ):
            for name in names:
                self.enterContext(
                    patch.object(module, name, rebase(getattr(module, name)))
                )

        for module, names in (
            (generator, ("REQUIRED_RUNTIME_ASSETS", "REQUIRED_HARNESS_WORKFLOWS")),
            (
                harness,
                (
                    "REQUIRED_ROOT_DOCS",
                    "REQUIRED_DIRS",
                    "REQUIRED_WORKFLOWS",
                    "REQUIRED_RUNTIME_ASSETS",
                ),
            ),
        ):
            for name in names:
                paths = tuple(rebase(path) for path in getattr(module, name))
                self.enterContext(patch.object(module, name, paths))
        self.enterContext(
            patch.object(
                harness,
                "REQUIRED_DOC_MARKERS",
                {
                    rebase(path): markers
                    for path, markers in harness.REQUIRED_DOC_MARKERS.items()
                },
            )
        )

        for directory in harness.REQUIRED_DIRS:
            directory.mkdir(parents=True, exist_ok=True)
        for path in (
            *harness.REQUIRED_ROOT_DOCS,
            *harness.REQUIRED_RUNTIME_ASSETS,
            *harness.REQUIRED_WORKFLOWS,
        ):
            if path != generator.HARNESS_HEALTH_PATH:
                self.write(path, "# Fixture source\n")
        for path, markers in harness.REQUIRED_DOC_MARKERS.items():
            self.write(path, "# Fixture reference\n\n" + "\n".join(markers))
        self.write(generator.DOCS_ROOT / "README.md", "\n".join(harness.README_MARKERS))
        self.write(generator.GARDENING_SUMMARY_PATH, generator.GENERATED_COMMENT + "\n")
        self.write(
            generator.BOUNDARY_BASELINE_PATH, '{"version": 1, "violations": []}\n'
        )

    @staticmethod
    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def run_generator(*args: str) -> int:
        with (
            patch("sys.argv", ["build_repo_knowledge_index.py", *args]),
            redirect_stdout(io.StringIO()),
        ):
            return generator.main()

    def test_default_generation_writes_indexes_and_health_deterministically(
        self,
    ) -> None:
        assert self.run_generator() == 0
        indexes = generator.build_knowledge_docs()
        assert generator.HARNESS_HEALTH_PATH not in indexes
        assert generator.HARNESS_HEALTH_PATH.exists()
        assert "# Harness Health" in generator.HARNESS_HEALTH_PATH.read_text(
            encoding="utf-8"
        )
        first_run = {
            path: path.read_bytes()
            for path in (*indexes, generator.HARNESS_HEALTH_PATH)
        }
        assert self.run_generator() == 0
        assert {path: path.read_bytes() for path in first_run} == first_run
        errors: list[str] = []
        harness.check_generated_knowledge_docs(errors)
        harness.check_root_docs(errors)
        assert errors == []

    def test_validation_accepts_missing_or_stale_health_snapshot(self) -> None:
        assert self.run_generator() == 0
        for snapshot in (None, "A stale snapshot from another branch.\n"):
            with self.subTest(snapshot=snapshot):
                if snapshot is None:
                    generator.HARNESS_HEALTH_PATH.unlink()
                else:
                    self.write(generator.HARNESS_HEALTH_PATH, snapshot)
                errors: list[str] = []
                harness.check_generated_knowledge_docs(errors)
                harness.check_root_docs(errors)
                assert errors == []

    def test_validation_still_rejects_stale_committed_indexes(self) -> None:
        assert self.run_generator() == 0
        generator.HARNESS_HEALTH_PATH.unlink()
        self.write(
            generator.DOCS_ROOT / "references" / "new-reference.md", "# New reference\n"
        )
        errors: list[str] = []
        harness.check_generated_knowledge_docs(errors)
        expected_index = generator.DOCS_ROOT / "references" / "index.md"
        assert f"Generated knowledge doc is stale: {expected_index}" in errors

    def test_validation_still_requires_source_docs_assets_and_workflows(self) -> None:
        assert self.run_generator() == 0
        generator.HARNESS_HEALTH_PATH.unlink()
        cases = (
            (
                generator.DOCS_ROOT / "SECURITY.md",
                "Missing required root knowledge doc",
            ),
            (
                harness.REQUIRED_RUNTIME_ASSETS[0],
                "Missing required runtime harness asset",
            ),
            (harness.REQUIRED_WORKFLOWS[0], "Missing required harness workflow"),
        )
        for path, message in cases:
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                path.unlink()
                errors: list[str] = []
                harness.check_root_docs(errors)
                assert errors == [f"{message}: {path}"]
                self.write(path, content)

    def test_health_only_refreshes_current_sources_without_rewriting_indexes(
        self,
    ) -> None:
        assert self.run_generator() == 0
        indexes = {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in generator.build_knowledge_docs()
        }
        snapshot = generator.HARNESS_HEALTH_PATH.read_text(encoding="utf-8")
        expected_counts: dict[str, int] = {}
        for directory, label in (
            ("design-docs", "Design docs"),
            ("product-specs", "Product specs"),
            ("references", "References"),
            ("exec-plans/active", "Active ExecPlans"),
            ("exec-plans/completed", "Completed ExecPlans"),
        ):
            source_dir = generator.DOCS_ROOT / directory
            previous_count = len(
                [path for path in source_dir.glob("*.md") if path.name != "index.md"]
            )
            assert f"- {label}: `{previous_count}`" in snapshot
            self.write(source_dir / "new-source.md", "# New source\n")
            expected_counts[label] = previous_count + 1
        self.write(
            generator.BOUNDARY_BASELINE_PATH,
            json.dumps(
                {
                    "version": 1,
                    "violations": [
                        {"rule_id": "backend.cross_service_import"},
                        {"rule_id": "backend.cross_service_import"},
                        {"rule_id": "frontend.direct_http"},
                    ],
                }
            ),
        )
        missing_asset = generator.REQUIRED_RUNTIME_ASSETS[0]
        missing_workflow = generator.REQUIRED_HARNESS_WORKFLOWS[0]
        missing_asset.unlink()
        missing_workflow.unlink()

        assert self.run_generator("--health-only") == 0
        refreshed = generator.HARNESS_HEALTH_PATH.read_text(encoding="utf-8")
        assert refreshed != snapshot
        for label, count in expected_counts.items():
            assert f"- {label}: `{count}`" in refreshed
        assert "- Baseline entries: `3`" in refreshed
        assert "- `backend.cross_service_import`: `2`" in refreshed
        assert "- `frontend.direct_http`: `1`" in refreshed
        for path in (missing_asset, missing_workflow):
            assert f"- MISSING `{path.relative_to(self.root).as_posix()}`" in refreshed
        present_asset = generator.REQUIRED_RUNTIME_ASSETS[1]
        assert f"- OK `{present_asset.relative_to(self.root).as_posix()}`" in refreshed
        assert {
            path: (path.read_bytes(), path.stat().st_mtime_ns) for path in indexes
        } == indexes

    def test_health_only_does_not_create_missing_indexes(self) -> None:
        assert self.run_generator("--health-only") == 0
        assert generator.HARNESS_HEALTH_PATH.exists()
        assert all(not path.exists() for path in generator.build_knowledge_docs())


if __name__ == "__main__":
    unittest.main()
