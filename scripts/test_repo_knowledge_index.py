#!/usr/bin/env python3
"""Protect committed knowledge indexes and optional local health snapshots."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import build_repo_knowledge_index as generator
import check_repo_harness as harness
import run_harness_gardening as gardening


class RepoKnowledgeIndexTest(unittest.TestCase):
    """Exercise real generation and validation against an isolated repository."""

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
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
                ("ROOT", "DOCS_ROOT", "BOUNDARY_BASELINE"),
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

        for path in (self.root / "docs/design-docs").glob("*.md"):
            self.write(
                path,
                '---\ntitle: Fixture\nstatus: draft\nowner_surface: repo\nlast_reviewed: ""\ncanonical: true\n---\n'
                + path.read_text(),
            )
        self.write(
            self.root / ".gitignore",
            "docs/generated/harness-health.md\ndocs/generated/harness-gardening-summary.md\n",
        )
        self.track()

    def track(self) -> None:
        """Stage fixture sources so discovery uses the same Git contract as CI."""
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)

    def fixture(self, name: str, content: str) -> Path:
        """Create and stage one tracked source, retaining unstaged tests separately."""
        path = self.root / name
        self.write(path, content)
        self.track()
        return path

    def test_partial_document_staging_cannot_hide_broken_index_links(self) -> None:
        """An unstaged link repair cannot make a broken staged document pass."""
        self.fixture("docs/references/target.md", "# Target\n")
        for index, suffix in enumerate(("md", "mdx", "MD")):
            with self.subTest(suffix=suffix):
                relative = f"docs/references/partial-{index}.{suffix}"
                path = self.fixture(relative, "# Partial\n[Broken](missing.md)\n")
                staged = subprocess.check_output(
                    ["git", "show", ":" + relative], cwd=self.root
                )
                self.write(path, "# Partial\n[Fixed](target.md)\n")
                link_errors: list[str] = []
                harness.check_local_document_links([path], link_errors)
                assert link_errors == []
                errors: list[str] = []
                harness.check_document_staging(errors)
                assert len(errors) == 1
                assert f"Partially staged document: {relative}." in errors[0]
                assert (
                    subprocess.check_output(
                        ["git", "show", ":" + relative], cwd=self.root
                    )
                    == staged
                )
                self.track()
                errors = []
                harness.check_document_staging(errors)
                assert errors == []

    def test_staging_guard_ignores_untracked_docs_and_non_document_edits(self) -> None:
        """The guard stays scoped to split versions of staged Markdown/MDX."""
        path = self.fixture("notes.txt", "staged text\n")
        self.write(path, "unstaged text\n")
        self.write(self.root / "untracked.md", "# Draft\n")
        errors: list[str] = []
        harness.check_document_staging(errors)
        assert errors == []

    def test_unstaged_anchor_edits_cannot_validate_a_new_staged_link(self) -> None:
        """A link target's unstaged content is part of the same validation graph."""
        target = self.fixture("docs/target.md", "# Original\n")
        tree = subprocess.check_output(
            ["git", "write-tree"], cwd=self.root, text=True
        ).strip()
        commit = subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.test",
                "commit-tree",
                tree,
                "-m",
                "test: establish fixture history",
            ],
            cwd=self.root,
            text=True,
        ).strip()
        subprocess.run(["git", "update-ref", "HEAD", commit], cwd=self.root, check=True)
        source = self.fixture("docs/links.md", "[new anchor](target.md#new)\n")
        self.write(target, "# New\n")
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert errors == []
        harness.check_document_staging(errors)
        assert len(errors) == 1
        assert "Unstaged document dependency: docs/target.md." in errors[0]
        self.track()
        errors = []
        harness.check_document_staging(errors)
        assert errors == []

    def test_scalar_quotes_preserve_malformed_dates_and_title_apostrophes(self) -> None:
        """Unmatched quotes remain visible to the date scanner and index."""
        root = self.root / "quoted-review-fixture"
        docs = root / "docs"
        path = docs / "product-specs" / "review.md"
        for raw, expected in (
            ('"2026-09-26"', "2026-09-26"),
            ("'2026-09-26'", "2026-09-26"),
            ("'2026-09-26", "'2026-09-26"),
            ("2026-09-26'", "2026-09-26'"),
            ("'2026-09-26\"", "'2026-09-26\""),
        ):
            with self.subTest(raw=raw):
                self.write(
                    path, "---\ntitle: Teachers'\nlast_reviewed: " + raw + "\n---\n"
                )
                metadata = generator.parse_frontmatter(path)
                assert metadata["title"] == "Teachers'"
                assert metadata["last_reviewed"] == expected
                if expected != "2026-09-26":
                    with (
                        patch.object(gardening, "ROOT", root),
                        patch.object(gardening, "DOCS_ROOT", docs),
                    ):
                        assert gardening.stale_review_docs() == [
                            "docs/product-specs/review.md (invalid last_reviewed="
                            + expected
                            + ")"
                        ]

    def test_unknown_review_dates_remain_missing_review_debt(self) -> None:
        """Accept an explicit empty date without pretending the review happened."""
        root = self.root / "review-fixture"
        docs = root / "docs"
        path = docs / "product-specs" / "unknown-review.md"
        with (
            patch.object(harness, "DOCS_ROOT", docs),
            patch.object(gardening, "ROOT", root),
            patch.object(gardening, "DOCS_ROOT", docs),
        ):
            for value in ('""', "''", ""):
                with self.subTest(value=value):
                    self.write(
                        path,
                        "---\ntitle: Pending review\nstatus: needs-review\n"
                        "owner_surface: repo\nlast_reviewed: "
                        + value
                        + "\ncanonical: true\n---\n",
                    )
                    assert generator.parse_frontmatter(path)["last_reviewed"] == ""
                    errors: list[str] = []
                    harness.check_frontmatter_docs(errors)
                    assert errors == []
                    assert gardening.stale_review_docs() == [
                        "docs/product-specs/unknown-review.md (missing last_reviewed)"
                    ]
            self.write(path, path.read_text().replace("last_reviewed: \n", ""))
            errors = []
            harness.check_frontmatter_docs(errors)
            assert any("last_reviewed" in error for error in errors)

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
        first_run = {path: path.read_bytes() for path in indexes}
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

    def test_inventory_covers_tracked_markdown_mdx_and_aliases(self) -> None:
        """Cover all tracked document classes without indexing local scratch files."""
        cases = {
            "AGENTS.md": ("# Rules", "instruction"),
            "src/web/SKILL.md": ("# Router", "skill-router"),
            "src/web/skills/example/SKILL.md": (
                "---\nname: example\ndescription: Use for examples.\n---\n# Example",
                "skill",
            ),
            "docs/history/old.md": ("# Old", "history"),
            "docs/exec-plans/active/current.md": ("# Current", "exec-plan-active"),
            "src/help.MDX": ("# Help", "reference"),
            ".github/copilot-instructions.md": ("See AGENTS.md", "alias"),
        }
        for name, (content, _category) in cases.items():
            self.fixture(name, content)
        alias = self.root / "GEMINI.md"
        alias.symlink_to("AGENTS.md")
        self.track()
        self.write(self.root / "scratch.md", "# Not committed")
        records = {
            str(record.path.relative_to(self.root)): record
            for record in generator.build_tracked_records()
        }
        for name, (_content, category) in cases.items():
            assert records[name].category == category
            assert records[name].last_reviewed == ""
        assert records["GEMINI.md"].category == "alias"
        assert records["docs/exec-plans/active/current.md"].canonical == "true"
        assert "scratch.md" not in records
        assert "docs/generated/harness-health.md" not in records
        assert "docs/generated/harness-gardening-summary.md" not in records
        assert set(records) == {
            str(path.relative_to(self.root)) for path in generator.tracked_markdown()
        }

    def test_wrapped_skill_descriptions_are_preserved(self) -> None:
        """Existing wrapped and folded metadata retains the whole trigger text."""
        for start in ("Use for", ">\n  Use for"):
            skill = self.fixture(
                "src/api/skills/example/SKILL.md",
                f"---\nname: example\ndescription: {start}\n  examples and retries.\n---\n# Example",
            )
            assert (
                generator.parse_frontmatter(skill)["description"]
                == "Use for examples and retries."
            )
            catalog = generator.render_skill_catalog("api", [skill])
            assert "Use for examples and retries." in catalog

    def test_skill_catalog_detects_omission_and_new_skills(self) -> None:
        """A newly staged skill invalidates the committed catalog until regeneration."""
        assert self.run_generator() == 0
        skill = self.fixture(
            "src/web/skills/added/SKILL.md",
            "---\nname: added\ndescription: Use for added workflows.\n---\n# Added",
        )
        errors: list[str] = []
        harness.check_generated_knowledge_docs(errors)
        assert any("src/web/skills/README.md" in error for error in errors)
        assert self.run_generator() == 0
        catalog = skill.parent.parent / "README.md"
        assert "[added](added/SKILL.md)" in catalog.read_text()
        self.write(catalog, generator.GENERATED_COMMENT + "\n# Incomplete catalog\n")
        errors = []
        harness.check_generated_knowledge_docs(errors)
        assert any("src/web/skills/README.md" in error for error in errors)

    def test_skill_metadata_accepts_valid_and_rejects_missing_or_duplicate(
        self,
    ) -> None:
        """Focused skills need usable triggers and globally unambiguous slugs."""
        valid = self.fixture(
            "src/web/skills/example/SKILL.md",
            "---\nname: example\ndescription: Use for examples.\n---\n# Example",
        )
        errors: list[str] = []
        harness.check_skill_metadata([valid], errors)
        assert errors == []
        for body in (
            "# No metadata",
            "---\nname: other\ndescription: \n---\n# Invalid",
        ):
            invalid = self.fixture("src/web/skills/invalid/SKILL.md", body)
            errors = []
            harness.check_skill_metadata([invalid], errors)
            assert any("directory slug" in error for error in errors)
            assert any("description" in error for error in errors)
        duplicate = self.fixture("src/api/skills/example/SKILL.md", valid.read_text())
        errors = []
        harness.check_skill_metadata([valid, duplicate], errors)
        assert any("Duplicate skill name" in error for error in errors)

    def test_link_targets_must_survive_a_clean_checkout(self) -> None:
        """Existing untracked, ignored, and empty local directories are not targets."""
        ignore = self.root / ".gitignore"
        self.fixture(".gitignore", ignore.read_text() + "docs/ignored.md\n")
        source = self.fixture(
            "docs/links.md",
            "[untracked](untracked.md)\n[ignored](ignored.md)\n[empty](local-only/)\n",
        )
        self.write(self.root / "docs/untracked.md", "# Local only\n")
        self.write(self.root / "docs/ignored.md", "# Ignored\n")
        (self.root / "docs/local-only").mkdir()
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 3
        assert all("Untracked local document link target" in error for error in errors)

    def test_removed_index_target_is_rejected_even_when_file_remains(self) -> None:
        """A staged deletion cannot be hidden by a leftover working-tree file."""
        source = self.fixture("docs/links.md", "[removed](removed.md)\n")
        target = self.fixture("docs/removed.md", "# Removed\n")
        subprocess.run(
            ["git", "rm", "--cached", "--quiet", "docs/removed.md"],
            cwd=self.root,
            check=True,
        )
        assert target.exists()
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 1
        assert "Untracked local document link target" in errors[0]

    def test_worktree_file_cannot_mask_an_indexed_broken_symlink(self) -> None:
        """A non-document type change must not repair the pending commit locally."""
        source = self.fixture("docs/links.md", "[asset](asset.svg)\n")
        target = self.root / "docs/asset.svg"
        target.symlink_to("missing.svg")
        self.track()
        target.unlink()
        self.write(target, "<svg/>\n")
        staging_errors: list[str] = []
        harness.check_document_staging(staging_errors)
        assert staging_errors == []  # Non-document edits are otherwise allowed.
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 1
        assert "asset.svg" in errors[0]
        self.track()
        for mode in ("-x", "+x"):
            subprocess.run(
                ["git", "update-index", f"--chmod={mode}", "docs/asset.svg"],
                cwd=self.root,
                check=True,
            )
            errors = []
            harness.check_local_document_links([source], errors)
            assert errors == []

    def test_tracked_aliases_cannot_hide_local_only_link_paths(self) -> None:
        """A tracked target does not make an untracked alias portable to CI."""
        self.fixture("docs/target.md", "# Target\n")
        alias = self.root / "docs/alias.md"
        alias.symlink_to("target.md")
        source = self.fixture(
            "docs/links.md",
            "[valid](alias.md#target)\n[local alias](local.md#target)\n[dir](./)\n",
        )
        (self.root / "docs/local.md").symlink_to("target.md")
        errors: list[str] = []
        harness.check_local_document_links([source, alias], errors)
        assert len(errors) == 1
        assert "local.md" in errors[0]
        self.write(source, "[alias](alias.md#target)\n")
        alias.unlink()
        alias.symlink_to("local.md")
        errors = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 1  # The alias differs from its indexed target.
        subprocess.run(["git", "add", "docs/alias.md"], cwd=self.root, check=True)
        errors = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 1  # The indexed alias still needs its untracked hop.
        self.track()
        errors = []
        harness.check_local_document_links([source, alias], errors)
        assert errors == []

    def test_local_links_resolve_reference_links_and_encoded_paths(self) -> None:
        """Links use the source location; code examples and remote links are not fetched."""
        self.fixture("docs/linked file.md", "# Linked")
        source = self.fixture(
            "docs/links.md",
            """# Links
[valid](linked%20file.md#linked)
[angle destination](<linked file.md>)
[reference][target]
[external](https://example.com/does-not-need-a-fetch)
![image](linked%20file.md)

[target]: linked%20file.md

```markdown
[example](not-a-real-example.md)
```
""",
        )
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert errors == []
        self.write(source, "[broken](missing.md)\n[escape](../../outside.md)")
        harness.check_local_document_links([source], errors)
        assert len(errors) == 2

    def test_local_anchors_html_and_mdx_literal_links(self) -> None:
        """Validate duplicate headings, explicit anchors and static MDX navigation."""
        target = self.fixture(
            "docs/target.md", '# Repeated\n# Repeated\n<a id="named"></a>'
        )
        source = self.fixture(
            "docs/source.mdx",
            '[second](target.md#repeated-1)\n<a href="target.md#named">named</a>\n<a href={dynamic}>dynamic</a>',
        )
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert errors == []
        self.write(source, '[broken](target.md#missing)\n<img src="gone.svg" />')
        harness.check_local_document_links([source], errors)
        assert len(errors) == 2
        assert target.exists()

    def test_historical_links_exempt_retired_runtime_paths_only(self) -> None:
        """Historical code references are not current contracts; doc navigation still works."""
        history = self.fixture("docs/history/old.md", "[retired](../../deleted.py)")
        errors: list[str] = []
        harness.check_local_document_links([history], errors)
        assert errors == []
        self.write(history, "[missing doc](missing.md)")
        harness.check_local_document_links([history], errors)
        assert len(errors) == 1
        current = self.fixture("docs/current.md", "[retired](../deleted.py)")
        errors = []
        harness.check_local_document_links([current], errors)
        assert len(errors) == 1

    def test_historical_document_directories_must_resolve(self) -> None:
        """The runtime exception must not hide broken historical doc navigation."""
        source = self.fixture(
            "docs/history/old.md",
            "[docs](../design-docs/)\n[missing](../retired-docs/)",
        )
        errors: list[str] = []
        harness.check_local_document_links([source], errors)
        assert len(errors) == 1
        assert "retired-docs" in errors[0]

    def test_gardening_and_validation_share_review_date_syntax(self) -> None:
        """Compact/week ISO dates cannot pass one checker and fail the other."""
        source = self.root / "docs/product-specs/date-format.md"
        with (
            patch.object(gardening, "DOCS_ROOT", self.root / "docs"),
            patch.object(gardening, "ROOT", self.root),
        ):
            for reviewed, invalid in (
                ("2026-01-01", False),
                ("20260926", True),
                ("2026-W39-6", True),
                ("2026-02-31", True),
            ):
                self.write(
                    source, f"---\nlast_reviewed: {reviewed}\n---\n# Date format"
                )
                errors: list[str] = []
                harness.check_review_dates([source], errors)
                assert bool(errors) == invalid
                hits = [
                    hit
                    for hit in gardening.stale_review_docs()
                    if "date-format.md" in hit and "invalid last_reviewed" in hit
                ]
                assert bool(hits) == invalid

    def test_broken_alias_is_reported(self) -> None:
        """Do not follow or silently accept a broken compatibility alias."""
        alias = self.root / "GEMINI.md"
        alias.symlink_to("missing.md")
        self.track()
        errors: list[str] = []
        harness.check_local_document_links([alias], errors)
        assert any("alias" in error for error in errors)

    def test_plan_lifecycle_preserves_external_acceptance_and_warns_without_archiving(
        self,
    ) -> None:
        """Only pending work in a completed plan fails; active closure is a review decision."""
        body = "# Plan\n\n" + "\n\n".join(
            f"## {heading}\n\nContext." for heading in harness.PLAN_HEADINGS
        )
        active = self.fixture(
            "docs/exec-plans/active/example.md",
            body + "\n- [ ] Verify real SMTP delivery.\n",
        )
        errors: list[str] = []
        warnings: list[str] = []
        harness.check_plan_lifecycle([active], errors, warnings)
        assert errors == warnings == []
        self.write(active, body + "\n- [x] Recorded acceptance.\n")
        harness.check_plan_lifecycle([active], errors, warnings)
        assert errors == []
        assert len(warnings) == 1
        assert active.exists()
        archived = self.fixture(
            "docs/exec-plans/completed/example.md",
            body + "\n- [ ] Verify real SMTP delivery.\n",
        )
        harness.check_plan_lifecycle([archived], errors, warnings)
        assert any("pending work" in error for error in errors)
        self.write(
            archived,
            body
            + "\n- [x] Delivery verified.\n```markdown\n- [ ] Example only.\n```\n",
        )
        errors = []
        harness.check_plan_lifecycle([archived], errors, [])
        assert errors == []

    def test_plan_headings_ignore_code_and_history_is_not_a_plan(self) -> None:
        """A fenced template is not a usable plan; historical checklists stay historical."""
        body = "\n".join("## " + heading for heading in harness.PLAN_HEADINGS)
        active = self.fixture(
            "docs/exec-plans/active/example.md", "```markdown\n" + body + "\n```"
        )
        errors: list[str] = []
        harness.check_plan_lifecycle([active], errors, [])
        assert len(errors) == len(harness.PLAN_HEADINGS)
        history = self.fixture(
            "docs/history/draft.md", "# Old draft\n- [ ] Old proposal"
        )
        errors = []
        harness.check_plan_lifecycle([history], errors, [])
        assert errors == []

    def test_unknown_review_dates_are_allowed_without_fabrication(self) -> None:
        """Unknown dates remain blank; impossible review dates fail separately."""
        doc = self.fixture(
            "docs/product-specs/example.md",
            '---\ntitle: Example\nstatus: needs-review\nowner_surface: repo\nlast_reviewed: ""\ncanonical: true\n---\n# Example',
        )
        errors: list[str] = []
        harness.check_frontmatter_docs(errors)
        harness.check_review_dates([doc], errors)
        assert errors == []
        record = next(
            record for record in generator.build_tracked_records() if record.path == doc
        )
        assert record.last_reviewed == ""
        for reviewed in ("not-a-date", "20260926", "2026-W39-6", "9999-01-01"):
            self.write(doc, f"---\nlast_reviewed: {reviewed}\n---\n# Example")
            errors = []
            harness.check_review_dates([doc], errors)
            assert len(errors) == 1

    def test_health_and_gardening_reports_have_provenance_and_are_optional(
        self,
    ) -> None:
        """Both ephemeral reports identify their checkout and UTC generation time."""
        assert self.run_generator() == 0
        report = generator.HARNESS_HEALTH_PATH.read_text()
        assert "Checkout HEAD:" in report
        timestamp = report.split("Generated at (UTC): `")[1].split("`")[0]
        assert timestamp.endswith("Z")
        assert datetime.fromisoformat(timestamp).utcoffset().total_seconds() == 0
        path = self.root / "garden.md"
        gardening.write_summary(
            path, stale_docs=["needs review"], retired_terms=[], stale_baseline=[]
        )
        assert "scripts/run_harness_gardening.py" in path.read_text()
        assert "Generated at (UTC):" in path.read_text()
        assert "Checkout HEAD:" in path.read_text()
        generator.GARDENING_SUMMARY_PATH.unlink()
        generator.HARNESS_HEALTH_PATH.unlink()
        errors: list[str] = []
        harness.check_root_docs(errors)
        assert errors == []


if __name__ == "__main__":
    unittest.main()
