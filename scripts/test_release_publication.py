# ruff: noqa: INP001, PT027 -- Standalone release regressions use stdlib unittest fixtures.
"""Exercise automatic publication and frozen-source recovery with mocked GitHub writes."""

from __future__ import annotations

import json
import os
import sys
import unittest
from contextlib import chdir
from unittest import mock

import release_workflow as release
import test_release_workflow as fixtures


class ReleasePublicationTests(unittest.TestCase):
    """Keep Git history real while all release/ref requests stay in memory."""

    def setUp(self) -> None:
        """Reuse the product's owned-version and merged-PR fixture."""
        self.fixture = fixtures.ReleaseFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def remote(self, source: str, *, record: dict | None = None) -> tuple[dict, object]:
        """Extend the existing explicit GitHub mock with release publication only."""
        state, api = self.fixture.fake_github(source, tag_sha=source, record=record)

        def github(
            method: str,
            path: str,
            payload: dict | None = None,
            *,
            missing_ok: bool = False,
        ) -> object:
            if method == "PATCH":
                assert path == "repos/fixture/product/releases/7"
                state["calls"].append((method, path, payload))
                state["release"].update(payload)
                return dict(state["release"])
            return api(method, path, payload, missing_ok=missing_ok)

        return state, github

    def test_manual_recovery_keeps_original_source_after_main_advances(self) -> None:
        """An explicit SHA, not dispatch HEAD, selects the candidate version."""
        fixture = self.fixture
        source = fixture.candidate()
        fixture.versions("3.0.2")
        newer = fixture.commit("chore: another version reaches main")
        fixture.git("tag", "v3.0.2")
        fixture.git("update-ref", "refs/remotes/origin/main", newer)
        event = {
            "inputs": {"source_commit": source, "expected_version": "3.0.1"},
        }
        with (
            chdir(fixture.repo),
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REF": "refs/heads/main",
                },
            ),
        ):
            values = release.detect(source, event)
        assert values == {
            "create_draft": "true",
            "commit": source,
            "version": "3.0.1",
            "tag": "v3.0.1",
            "previous_tag": "v3.0.0",
        }
        assert fixture.git("rev-parse", "HEAD") == newer

    def test_manual_recovery_requires_main_original_sha_and_matching_version(
        self,
    ) -> None:
        """Malformed or stale manual inputs fail before remote release operations."""
        fixture = self.fixture
        source = fixture.candidate()
        for case in ("branch", "tag", "source", "version", "short-sha", "missing"):
            with self.subTest(case=case):
                event = {
                    "inputs": {"source_commit": source, "expected_version": "3.0.1"},
                }
                selected = source
                ref = "refs/heads/main"
                if case == "branch":
                    ref = "refs/heads/development"
                elif case == "tag":
                    ref = "refs/tags/v3.0.1"
                elif case == "source":
                    event["inputs"]["source_commit"] = fixture.base
                elif case == "version":
                    event["inputs"]["expected_version"] = "3.0.2"
                elif case == "short-sha":
                    selected = source[:7]
                else:
                    event["inputs"].pop("source_commit")
                with (
                    chdir(fixture.repo),
                    mock.patch.dict(
                        os.environ,
                        {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": ref},
                    ),
                    self.assertRaises(ValueError),
                ):
                    release.detect(selected, event)

    def test_stage_images_publication_and_legacy_event_share_the_same_source(
        self,
    ) -> None:
        """Only publication changes the draft state and records completed image work."""
        fixture = self.fixture
        source = fixture.candidate()
        event = json.loads(fixture.event(source).read_text())
        state, api = self.remote(source)
        with chdir(fixture.repo), mock.patch.object(release, "github", side_effect=api):
            release.create_draft(source, event, "fixture/product", "Product notes")
            assert state["release"]["draft"] is True
            assert release.IMAGES_MARKER not in state["release"]["body"]
            assert not any(method == "PATCH" for method, _, _ in state["calls"])
            values = release.validate_candidate(source, "v3.0.1", "fixture/product")
            assert values["should_build"] == "true"
            assert values["commit"] == source
            state["release"]["body"] += "\nMaintainer notes.\n"
            original_notes = state["release"]["body"]
            url = release.publish_release(source, "v3.0.1", "fixture/product")
            assert url == state["release"]["html_url"]
            assert state["release"]["draft"] is False
            assert original_notes.rstrip() in state["release"]["body"]
            assert release.images_verified(state["release"], source)
            writes = [
                payload for method, _, payload in state["calls"] if method == "PATCH"
            ]
            assert len(writes) == 1
            assert writes[0]["draft"] is False
            assert writes[0]["prerelease"] is False
            assert writes[0]["make_latest"] == "legacy"
            values = release.validate_published(
                source,
                {"action": "published", "release": dict(state["release"])},
                "fixture/product",
            )
            assert values["should_build"] == "false"

    def test_failed_image_attempt_remains_a_draft_and_reuses_original_notes(
        self,
    ) -> None:
        """Recovery before publication never opens a public Release by itself."""
        fixture = self.fixture
        source = fixture.candidate()
        event = json.loads(fixture.event(source).read_text())
        state, api = self.remote(source)
        with chdir(fixture.repo), mock.patch.object(release, "github", side_effect=api):
            release.create_draft(source, event, "fixture/product", "Original notes")
            state["release"]["body"] += "\nHuman edit.\n"
            state["calls"].clear()
            release.create_draft(
                source,
                event,
                "fixture/product",
                "Recomputed notes",
                resume_published=True,
            )
            assert (
                release.validate_candidate(source, "v3.0.1", "fixture/product")[
                    "should_build"
                ]
                == "true"
            )
        assert state["release"]["draft"] is True
        assert "Original notes" in state["release"]["body"]
        assert "Human edit." in state["release"]["body"]
        assert all(method == "GET" for method, _, _ in state["calls"])

    def test_publication_success_readback_failure_is_recoverable_without_writes(
        self,
    ) -> None:
        """A retry accepts only the exact public candidate that already completed."""
        fixture = self.fixture
        source = fixture.candidate()
        record = fixture.release_record(source)
        state, api = self.remote(source, record=record)
        interrupt = True

        def interrupted(
            method: str,
            path: str,
            payload: dict | None = None,
            *,
            missing_ok: bool = False,
        ) -> object:
            nonlocal interrupt
            result = api(method, path, payload, missing_ok=missing_ok)
            if (
                method == "GET"
                and path.endswith("/releases/7")
                and not record["draft"]
                and interrupt
            ):
                interrupt = False
                message = "Readback interrupted after successful publication"
                raise OSError(message)
            return result

        with (
            chdir(fixture.repo),
            mock.patch.object(release, "github", side_effect=interrupted),
        ):
            with self.assertRaisesRegex(OSError, "Readback interrupted"):
                release.publish_release(source, "v3.0.1", "fixture/product")
            assert record["draft"] is False
            assert release.images_verified(record, source)
            fixture.versions("3.0.2")
            newer = fixture.commit("chore: main advances after publication")
            fixture.git("update-ref", "refs/remotes/origin/main", newer)
            state["calls"].clear()
            release.create_draft(
                source,
                json.loads(fixture.event(source).read_text()),
                "fixture/product",
                "Newly generated notes",
                resume_published=True,
            )
            assert (
                release.validate_candidate(source, "v3.0.1", "fixture/product")[
                    "should_build"
                ]
                == "false"
            )
            assert (
                release.publish_release(source, "v3.0.1", "fixture/product")
                == record["html_url"]
            )
        assert all(method == "GET" for method, _, _ in state["calls"])
        assert fixture.git("rev-parse", "HEAD") == newer

    def test_publication_rejects_unowned_or_conflicting_candidates_before_writes(
        self,
    ) -> None:
        """Source, provenance, tag and prerelease checks survive the new retry path."""
        fixture = self.fixture
        source = fixture.candidate()
        for case in (
            "public",
            "prerelease",
            "target",
            "tag",
            "marker",
            "duplicate",
            "automation",
            "missing",
        ):
            with self.subTest(case=case):
                record = fixture.release_record(source)
                if case == "public":
                    record["draft"] = False
                elif case == "prerelease":
                    record["prerelease"] = True
                elif case == "target":
                    record["target_commitish"] = fixture.base
                elif case == "marker":
                    record["body"] += f"\n{release.IMAGES_MARKER}{fixture.base} -->"
                elif case == "duplicate":
                    record["body"] += 2 * f"\n{release.IMAGES_MARKER}{source} -->"
                state, api = self.remote(
                    source, record=None if case == "missing" else record
                )
                if case == "tag":
                    state["tag"] = fixture.base
                elif case == "automation":
                    state["pr"]["merged_by"]["type"] = "Bot"
                with (
                    chdir(fixture.repo),
                    mock.patch.object(release, "github", side_effect=api),
                    self.assertRaises(ValueError),
                ):
                    release.publish_release(source, "v3.0.1", "fixture/product")
                assert all(method == "GET" for method, _, _ in state["calls"]), case

    def test_publication_verifies_final_state_body_marker_and_tag(self) -> None:
        """Successful PATCH responses cannot hide incomplete or changed publication."""
        fixture = self.fixture
        source = fixture.candidate()
        for case in ("draft", "prerelease", "notes", "tag", "marker"):
            with self.subTest(case=case):
                record = fixture.release_record(source)
                state, api = self.remote(source, record=record)

                def corrupt(
                    method: str,
                    path: str,
                    payload: dict | None = None,
                    *,
                    missing_ok: bool = False,
                    case: str = case,
                    record: dict = record,
                    api: object = api,
                    state: dict = state,
                ) -> object:
                    result = api(method, path, payload, missing_ok=missing_ok)
                    if method == "PATCH":
                        if case in {"draft", "prerelease"}:
                            record[case] = True
                        elif case == "notes":
                            record["body"] += "\nUnexpected body change"
                        elif case == "tag":
                            state["tag"] = fixture.base
                        else:
                            record["body"] = record["body"].replace(
                                release.IMAGES_MARKER, "removed:"
                            )
                    return result

                with (
                    chdir(fixture.repo),
                    mock.patch.object(release, "github", side_effect=corrupt),
                    self.assertRaises(ValueError),
                ):
                    release.publish_release(source, "v3.0.1", "fixture/product")

    def test_legacy_events_only_skip_fully_validated_completed_releases(self) -> None:
        """Unmarked manual publication retains builds; malformed markers fail closed."""
        fixture = self.fixture
        source = fixture.candidate()
        for case in ("manual", "completed", "wrong-marker", "wrong-tag", "prerelease"):
            with self.subTest(case=case):
                record = fixture.release_record(source, draft=False)
                if case != "manual":
                    record["body"] += f"\n{release.IMAGES_MARKER}{source} -->"
                if case == "wrong-marker":
                    record["body"] = record["body"].replace(
                        f"{release.IMAGES_MARKER}{source}",
                        f"{release.IMAGES_MARKER}{fixture.base}",
                    )
                elif case == "prerelease":
                    record["prerelease"] = True
                state, api = self.remote(source, record=record)
                if case == "wrong-tag":
                    state["tag"] = fixture.base
                with (
                    chdir(fixture.repo),
                    mock.patch.object(release, "github", side_effect=api),
                ):
                    event = {"action": "published", "release": record}
                    if case in {"wrong-marker", "wrong-tag"}:
                        with self.assertRaises(ValueError):
                            release.validate_published(source, event, "fixture/product")
                    else:
                        result = release.validate_published(
                            source, event, "fixture/product"
                        )
                        assert result["should_build"] == (
                            "true" if case == "manual" else "false"
                        )
                assert all(method == "GET" for method, _, _ in state["calls"])

    def test_notes_cannot_forge_the_reserved_completion_marker(self) -> None:
        """A caller's generated notes cannot masquerade as coordinator state."""
        fixture = self.fixture
        source = fixture.candidate()
        state, api = self.remote(source)
        with (
            chdir(fixture.repo),
            mock.patch.object(release, "github", side_effect=api),
            self.assertRaisesRegex(ValueError, "reserved"),
        ):
            release.create_draft(
                source,
                json.loads(fixture.event(source).read_text()),
                "fixture/product",
                f"{release.IMAGES_MARKER}{source} -->",
                resume_published=True,
            )
        assert not state["calls"]

    def test_stage_and_publish_cli_write_verified_single_line_outputs(self) -> None:
        """Exercise public command parsing with real files and mocked GitHub only."""
        fixture = self.fixture
        source = fixture.candidate()
        event = fixture.event(source)
        notes = fixture.root / "notes.md"
        notes.write_text("Release notes\n")
        output = fixture.root / "stage-output"
        state, api = self.remote(source)
        with chdir(fixture.repo), mock.patch.object(release, "github", side_effect=api):
            for command, arguments in (
                ("stage", ["--event", str(event), "--notes", str(notes)]),
                ("publish", ["--tag", "v3.0.1"]),
            ):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "release_workflow.py",
                        command,
                        "--source",
                        source,
                        "--repository",
                        "fixture/product",
                        "--output",
                        str(output),
                        *arguments,
                    ],
                ):
                    release.main()
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["commit"] == source
        assert values["tag"] == "v3.0.1"
        assert values["should_build"] == "true"
        assert values["published"] == "true"
        assert state["release"]["draft"] is False

    def test_manual_stage_cli_recovers_public_source_read_only(self) -> None:
        """A manual rerun uses the old source even when the runtime checkout is newer."""
        fixture = self.fixture
        source = fixture.candidate()
        record = fixture.release_record(source, draft=False)
        record["body"] += f"\n{release.IMAGES_MARKER}{source} -->\n"
        state, api = self.remote(source, record=record)
        fixture.versions("3.0.2")
        newer = fixture.commit("chore: main moves beyond the recovered release")
        fixture.git("update-ref", "refs/remotes/origin/main", newer)
        event = fixture.root / "recovery.json"
        event.write_text(
            json.dumps(
                {
                    "inputs": {"source_commit": source, "expected_version": "3.0.1"},
                }
            )
        )
        notes = fixture.root / "notes.md"
        notes.write_text("Recomputed notes do not replace a public Release.\n")
        output = fixture.root / "recovery-output"
        with (
            chdir(fixture.repo),
            mock.patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_REF": "refs/heads/main",
                },
            ),
            mock.patch.object(release, "github", side_effect=api),
            mock.patch.object(
                sys,
                "argv",
                [
                    "release_workflow.py",
                    "stage",
                    "--source",
                    source,
                    "--repository",
                    "fixture/product",
                    "--event",
                    str(event),
                    "--notes",
                    str(notes),
                    "--output",
                    str(output),
                ],
            ),
        ):
            release.main()
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        assert values["commit"] == source
        assert values["should_build"] == "false"
        assert values["version"] == "3.0.1"
        assert all(method == "GET" for method, _, _ in state["calls"])
        assert fixture.git("rev-parse", "HEAD") == newer

    def test_public_recovery_never_recreates_a_missing_tag(self) -> None:
        """A published candidate with a lost tag needs investigation, not a write."""
        fixture = self.fixture
        source = fixture.candidate()
        record = fixture.release_record(source, draft=False)
        record["body"] += f"\n{release.IMAGES_MARKER}{source} -->\n"
        state, api = self.remote(source, record=record)
        state["tag"] = None
        with (
            chdir(fixture.repo),
            mock.patch.object(release, "github", side_effect=api),
            self.assertRaisesRegex(ValueError, "existing exact-source formal tag"),
        ):
            release.create_draft(
                source,
                json.loads(fixture.event(source).read_text()),
                "fixture/product",
                "Notes",
                resume_published=True,
            )
        assert all(method == "GET" for method, _, _ in state["calls"])

    def test_failed_publish_cli_emits_no_success_output(self) -> None:
        """Publication rejection propagates a failing command without published=true."""
        fixture = self.fixture
        source = fixture.candidate()
        record = fixture.release_record(source)
        record["prerelease"] = True
        state, api = self.remote(source, record=record)
        output = fixture.root / "failed-output"
        with (
            chdir(fixture.repo),
            mock.patch.object(release, "github", side_effect=api),
            mock.patch.object(
                sys,
                "argv",
                [
                    "release_workflow.py",
                    "publish",
                    "--source",
                    source,
                    "--tag",
                    "v3.0.1",
                    "--repository",
                    "fixture/product",
                    "--output",
                    str(output),
                ],
            ),
            self.assertRaises(SystemExit) as failure,
        ):
            release.main()
        assert failure.exception.code == 1
        assert not output.exists()
        assert all(method == "GET" for method, _, _ in state["calls"])


if __name__ == "__main__":
    unittest.main()
