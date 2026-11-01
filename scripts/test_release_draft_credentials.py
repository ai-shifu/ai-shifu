# ruff: noqa: INP001, PT027 -- Standalone workflow regressions use the repository's unittest fixtures.
"""Keep privileged release credentials separate from frozen-source release guards."""

from __future__ import annotations

import json
import os
import unittest
from contextlib import chdir
from pathlib import Path
from unittest import mock

import release_workflow as release
import test_release_workflow as fixtures
import yaml

ROOT = Path(__file__).resolve().parents[1]


class ReleaseDraftCredentialTests(unittest.TestCase):
    """Read the real workflow and exercise Git guards with mocked remote writes."""

    def setUp(self) -> None:
        self.fixture = fixtures.ReleaseFixture()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_only_release_writes_can_select_the_workflow_capable_pat(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/draft-release.yml").read_text()
        )
        job = workflow["jobs"]["draft"]
        steps = {step.get("id"): step for step in job["steps"] if step.get("id")}
        mutation = steps["release"]
        assert mutation["env"]["GH_TOKEN"] == (
            "${{ secrets.PAT_TOKEN || github.token }}"  # noqa: S105 -- This is a workflow expression, not a credential.
        )
        assert mutation["if"] == "steps.source.outputs.create_draft == 'true'"
        assert '--source "$RELEASE_SOURCE"' in mutation["run"]
        assert '--event "$GITHUB_EVENT_PATH"' in mutation["run"]
        notes = next(
            step
            for step in job["steps"]
            if "scripts/release_notes.py" in step.get("run", "")
        )
        assert notes["env"]["GH_TOKEN"] == "${{ github.token }}"  # noqa: S105 -- This is a workflow expression, not a credential.
        assert all(
            "secrets.PAT_TOKEN" not in str(step)
            for step in job["steps"]
            if step is not mutation
        )
        checkout = next(
            step for step in job["steps"] if "actions/checkout" in step.get("uses", "")
        )
        assert checkout["with"]["ref"] == "${{ github.workflow_sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert job["permissions"] == {"contents": "write", "pull-requests": "read"}
        publication = workflow["jobs"]["publish"]
        write = next(
            step for step in publication["steps"] if step.get("id") == "publication"
        )
        assert write["env"]["GH_TOKEN"] == mutation["env"]["GH_TOKEN"]
        assert " publish " in write["run"]
        assert write["env"]["RELEASE_SOURCE"] == "${{ needs.draft.outputs.commit }}"
        assert all(
            "secrets.PAT_TOKEN" not in str(step)
            for step in publication["steps"]
            if step is not write
        )
        assert publication["permissions"] == job["permissions"]

    def test_retry_keeps_the_frozen_source_after_main_workflows_change(self) -> None:
        fixture = self.fixture
        fixture.write(".github/workflows/check.yml", "name: Before release\n")
        fixture.commit("ci: establish the workflow before release")
        source = fixture.candidate()
        event = json.loads(fixture.event(source).read_text())
        fixture.write(".github/workflows/check.yml", "name: After release\n")
        newer = fixture.commit("ci: update the workflow after release")
        fixture.git("update-ref", "refs/remotes/origin/main", newer)

        state, api = fixture.fake_github(source, tag_sha=source)
        with (
            chdir(fixture.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "workflow-capable-pat"}),
            mock.patch.object(release, "github", side_effect=api),
        ):
            release.create_draft(source, event, "fixture/product", "Notes")
            assert state["release"]["target_commitish"] == source
            assert state["tag"] == source
            assert fixture.git("rev-parse", "HEAD") == newer
            state["calls"].clear()
            state["release"]["body"] += "\nHuman-reviewed notes.\n"
            release.create_draft(source, event, "fixture/product", "New notes")
            assert all(method == "GET" for method, _, _ in state["calls"])
            assert "Human-reviewed notes." in state["release"]["body"]

    def test_pat_does_not_bypass_event_provenance_or_tag_conflicts(self) -> None:
        fixture = self.fixture
        source = fixture.candidate()
        for case in ("wrong-event", "automation", "tag-conflict"):
            with self.subTest(case=case):
                event = json.loads(fixture.event(source).read_text())
                state, api = fixture.fake_github(
                    source,
                    tag_sha=fixture.base if case == "tag-conflict" else source,
                )
                if case == "wrong-event":
                    event["after"] = fixture.base
                if case == "automation":
                    state["pr"]["merged_by"]["login"] = "ai-shifu-bot"
                with (
                    chdir(fixture.repo),
                    mock.patch.dict(os.environ, {"GH_TOKEN": "workflow-capable-pat"}),
                    mock.patch.object(release, "github", side_effect=api),
                    self.assertRaises(ValueError),
                ):
                    release.create_draft(source, event, "fixture/product", "Notes")
                assert all(method == "GET" for method, _, _ in state["calls"])


if __name__ == "__main__":
    unittest.main()
