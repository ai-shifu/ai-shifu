# ruff: noqa: INP001, PT027 -- Standalone tests retain stdlib unittest exception contexts for the CI runner.
"""Exercise the PR-first release contract with real Git, never remote writes."""

from __future__ import annotations

import io
import json
import os
import runpy
import shlex
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import chdir
from pathlib import Path
from unittest import mock

import release_notes as notes
import release_workflow as release
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_workflow.py"
ENGINE = "src/api/markdownflow/engine/__init__.py"
PACKAGES = ("src/web",)


class ReleaseFixture(unittest.TestCase):
    """Run the real CLI against an isolated Git repository."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        environment = mock.patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push"})
        environment.start()
        self.addCleanup(environment.stop)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.versions("3.0.0", legacy=True)
        self.write("README.md", "# Fixture\n\nA release fixture.\n")
        self.base = self.commit("feat: initial fixture (#1)")
        self.git("tag", "v3.0.0")
        self.git("update-ref", "refs/remotes/origin/main", self.base)

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def write(self, path: str, text: str) -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def versions(self, version: str, *, legacy: bool = False) -> None:
        for package in PACKAGES:
            self.write(
                f"{package}/package.json",
                json.dumps(
                    {
                        "name": "fixture",
                        "version": version,
                        "dependencies": {"unchanged": "1.2.3"},
                    }
                )
                + "\n",
            )
            self.write(
                f"{package}/package-lock.json",
                json.dumps(
                    {
                        "version": version,
                        "packages": {
                            "": {"version": version},
                            "node_modules/unchanged": {
                                "version": "1.2.3",
                            },
                        },
                    }
                )
                + "\n",
            )
        self.write(ENGINE, f'"""Fixture engine."""\n__version__ = "{version}"\n')
        web = "ai-shifu-cook-web" if legacy else "ai-shifu-web"
        self.write(
            "docker/docker-compose.yml",
            "services:\n"
            f"  web:\n    image: aishifu/{web}:v{version}\n"
            f"  api:\n    image: aishifu/ai-shifu-api:v{version}\n"
            f"  celery:\n    image: aishifu/ai-shifu-api:v{version}\n"
            "  redis:\n    image: redis:7-alpine\n",
        )
        self.write(
            "docker/docker-compose.latest.yml",
            "services:\n"
            "  web:\n    image: aishifu/ai-shifu-web:latest\n"
            "  api:\n    image: aishifu/ai-shifu-api:latest\n",
        )

    def commit(self, message: str) -> str:
        self.git("add", ".")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def invoke(
        self, *arguments: str, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            cwd=self.repo,
            env={**os.environ, **environment},
            check=False,
            capture_output=True,
            text=True,
        )

    def event(self, source: str, *, before: str | None = None) -> Path:
        path = self.root / "event.json"
        path.write_text(
            json.dumps(
                {
                    "ref": "refs/heads/main",
                    "after": source,
                    "before": before or self.base,
                    "deleted": False,
                    "forced": False,
                }
            )
        )
        return path

    def candidate(self, version: str = "3.0.1") -> str:
        self.versions(version)
        source = self.commit(f"chore: flow version to v{version} (#2)")
        self.git("update-ref", "refs/remotes/origin/main", source)
        return source

    def test_detect_freezes_event_source_not_newer_main_or_checkout(self) -> None:
        source = self.candidate()
        event = self.event(source)
        self.versions("3.0.2")
        newer = self.commit("chore: a later release (#3)")
        self.git("tag", "v3.0.2")
        self.git(
            "tag", "v3.0.1", source
        )  # A same-source rerun must exclude its own tag.
        self.git("update-ref", "refs/remotes/origin/main", newer)
        output = self.root / "outputs"
        result = self.invoke(
            "detect",
            "--source",
            source,
            "--event",
            str(event),
            "--output",
            str(output),
            GITHUB_EVENT_NAME="push",
        )
        assert result.returncode == 0, result.stderr
        assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
            "create_draft": "true",
            "commit": source,
            "version": "3.0.1",
            "tag": "v3.0.1",
            "previous_tag": "v3.0.0",
        }
        assert self.git("rev-parse", "HEAD") == newer

    def test_detect_skips_unchanged_and_missing_initial_baselines(self) -> None:
        for before in (self.base, "0" * 40):
            with self.subTest(before=before):
                output = self.root / f"skip-{before}"
                result = self.invoke(
                    "detect",
                    "--source",
                    self.base,
                    "--event",
                    str(self.event(self.base, before=before)),
                    "--output",
                    str(output),
                    GITHUB_EVENT_NAME="push",
                )
                assert result.returncode == 0, result.stderr
                assert "create_draft=false\n" in output.read_text()
        self.git("rm", primary := "src/web/package.json")
        missing = self.commit("chore: fixture without a primary version")
        source = self.candidate()
        output = self.root / "missing-primary"
        result = self.invoke(
            "detect",
            "--source",
            source,
            "--event",
            str(self.event(source, before=missing)),
            "--output",
            str(output),
            GITHUB_EVENT_NAME="push",
        )
        assert result.returncode == 0, f"{primary}: {result.stderr}"
        assert "create_draft=false\n" in output.read_text()

    def test_detect_rejects_invalid_events_versions_and_inconsistent_sources(
        self,
    ) -> None:
        cases = [
            "decrease",
            "malformed",
            "leading-zero",
            "forced",
            "deleted",
            "wrong-ref",
            "wrong-event",
            "wrong-after",
            "lock-root",
            "lock-top",
            "engine",
            "pinned",
            "rolling",
            "not-on-main",
            "bad-before",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.git("reset", "--hard", self.base)
                version = {
                    "decrease": "2.9.9",
                    "malformed": "3.0.1-rc.1",
                    "leading-zero": "03.0.1",
                }.get(case, "3.0.1")
                self.versions(version)
                if case in {"lock-root", "lock-top"}:
                    path = self.repo / "src/web/package-lock.json"
                    lock = json.loads(path.read_text())
                    if case == "lock-root":
                        lock["packages"][""]["version"] = "3.0.0"
                    else:
                        lock["version"] = "3.0.0"
                    path.write_text(json.dumps(lock))
                if case == "engine":
                    self.write(ENGINE, '__version__ = "3.0.0"\n')
                if case in {"pinned", "rolling"}:
                    name = (
                        "docker/docker-compose.yml"
                        if case == "pinned"
                        else "docker/docker-compose.latest.yml"
                    )
                    self.write(
                        name,
                        "services:\n  api:\n    image: aishifu/ai-shifu-api:v3.0.0\n",
                    )
                source = self.commit(f"chore: fixture {case}")
                self.git(
                    "update-ref",
                    "refs/remotes/origin/main",
                    self.base if case == "not-on-main" else source,
                )
                event = self.event(source)
                data = json.loads(event.read_text())
                if case in {"forced", "deleted"}:
                    data[case] = True
                if case == "wrong-ref":
                    data["ref"] = "refs/heads/feature"
                if case == "wrong-after":
                    data["after"] = self.base
                if case == "bad-before":
                    data["before"] = "main"
                event.write_text(json.dumps(data))
                output = self.root / f"reject-{case}"
                result = self.invoke(
                    "detect",
                    "--source",
                    source,
                    "--event",
                    str(event),
                    "--output",
                    str(output),
                    GITHUB_EVENT_NAME="workflow_dispatch"
                    if case == "wrong-event"
                    else "push",
                )
                assert result.returncode != 0, case
                assert not output.exists(), case

    def merged_pr(self, source: str) -> dict:
        return {
            "number": 2,
            "merged": True,
            "state": "closed",
            "merged_at": "2026-10-22T06:00:00Z",
            "merge_commit_sha": source,
            "auto_merge": None,
            "base": {"ref": "main", "repo": {"full_name": "fixture/product"}},
            "head": {
                "ref": "release/version-bump-v3.0.1",
                "repo": {"full_name": "fixture/product"},
            },
            "merged_by": {"login": "maintainer", "type": "User"},
        }

    def test_merged_release_pr_rejects_known_automation_and_auto_merge(self) -> None:
        """GitHub responses are mocked; Git ancestry/version transitions are real."""
        assert hasattr(release, "validate_provenance"), (
            "Merged release PR provenance guard is missing"
        )
        source = self.candidate()
        for case in (
            "valid",
            "known-user-bot",
            "bot-type",
            "bot-login",
            "auto-merge",
            "unmerged",
            "wrong-base",
            "wrong-head",
            "wrong-repo",
            "wrong-commit",
            "missing-merger",
            "no-pr",
        ):
            with self.subTest(case=case):
                pr = self.merged_pr(source)
                if case == "known-user-bot":
                    pr["merged_by"]["login"] = "ai-shifu-bot"
                if case == "bot-type":
                    pr["merged_by"]["type"] = "Bot"
                if case == "bot-login":
                    pr["merged_by"]["login"] = "automation[bot]"
                if case == "auto-merge":
                    pr["auto_merge"] = {"enabled_by": {"login": "maintainer"}}
                if case == "unmerged":
                    pr["merged"] = False
                if case == "wrong-base":
                    pr["base"]["ref"] = "develop"
                if case == "wrong-head":
                    pr["head"]["ref"] = "feature"
                if case == "wrong-repo":
                    pr["head"]["repo"]["full_name"] = "fork/product"
                if case == "wrong-commit":
                    pr["merge_commit_sha"] = self.base
                if case == "missing-merger":
                    pr["merged_by"] = None

                def github(
                    method: str,
                    path: str,
                    payload: dict | None = None,
                    *,
                    missing_ok: bool = False,
                    case: str = case,
                    pr: dict = pr,
                ) -> object:
                    assert method == "GET", "Provenance must never write to GitHub"
                    assert payload is None
                    assert not missing_ok
                    if "/commits/" in path:
                        return [] if case == "no-pr" else [{"number": 2}]
                    return pr

                with (
                    chdir(self.repo),
                    mock.patch.object(
                        release, "github", side_effect=github, create=True
                    ),
                ):
                    if case == "valid":
                        assert (
                            release.validate_provenance(
                                source, "3.0.1", "fixture/product"
                            )
                            == 2
                        )
                    else:
                        with self.assertRaises(ValueError):
                            release.validate_provenance(
                                source, "3.0.1", "fixture/product"
                            )

    def test_github_transport_uses_json_and_only_explicit_404_means_absent(
        self,
    ) -> None:
        """Mock HTTP transport only; no GitHub request is sent by this test."""
        assert hasattr(release, "github"), (
            "Authenticated GitHub JSON transport is missing"
        )
        payload = {"body": 'arbitrary " text\nEOF\n$(touch injected)', "draft": True}
        with mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}):
            with mock.patch.object(
                urllib.request, "urlopen", return_value=io.BytesIO(b'{"id": 7}')
            ) as send:
                assert release.github(
                    "POST", "repos/fixture/product/releases", payload
                ) == {"id": 7}
                request = send.call_args.args[0]
                assert request.get_method() == "POST"
                assert json.loads(request.data) == payload
                assert (
                    request.full_url
                    == "https://api.github.com/repos/fixture/product/releases"
                )
            for code in (404, 403, 500):
                with (
                    self.subTest(code=code),
                    mock.patch.object(
                        urllib.request,
                        "urlopen",
                        side_effect=urllib.error.HTTPError(
                            "https://api.github.com/fixture",
                            code,
                            "mock failure",
                            {},
                            None,
                        ),
                    ),
                ):
                    if code == 404:
                        assert (
                            release.github(
                                "GET",
                                "repos/fixture/product/releases/tags/v3.0.1",
                                missing_ok=True,
                            )
                            is None
                        )
                    else:
                        with self.assertRaises(urllib.error.HTTPError):
                            release.github(
                                "GET",
                                "repos/fixture/product/releases/tags/v3.0.1",
                                missing_ok=True,
                            )
                    with self.assertRaises(urllib.error.HTTPError):
                        release.github(
                            "GET", "repos/fixture/product/releases/tags/v3.0.1"
                        )

    def fake_github(
        self, source: str, *, tag_sha: str | None = None, record: dict | None = None
    ) -> tuple[dict, object]:
        """Mock GitHub explicitly; writes only mutate this Python dictionary."""
        state = {
            "tag": tag_sha,
            "release": record,
            "calls": [],
            "pr": self.merged_pr(source),
        }

        def github(
            method: str,
            path: str,
            payload: dict | None = None,
            *,
            missing_ok: bool = False,
        ) -> object:
            state["calls"].append((method, path, payload))
            if "/commits/" in path and "/pulls?" in path:
                return [{"number": 2}]
            if path.endswith("/pulls/2"):
                return state["pr"]
            if "/releases?" in path:
                return [] if state["release"] is None else [state["release"]]
            if "/git/ref/tags/" in path:
                assert missing_ok
                return (
                    None
                    if state["tag"] is None
                    else {"object": {"type": "commit", "sha": state["tag"]}}
                )
            if method == "POST" and path.endswith("/git/refs"):
                assert state["tag"] is None
                assert payload == {"ref": "refs/tags/v3.0.1", "sha": source}
                state["tag"] = source
                return {"object": {"type": "commit", "sha": source}}
            if method == "POST" and path.endswith("/releases"):
                assert state["release"] is None
                state["release"] = {
                    **payload,
                    "id": 7,
                    "html_url": "https://github.com/fixture/product/releases/untagged-fixture",
                }
                return dict(state["release"])
            if method == "GET" and path.endswith("/releases/7"):
                return dict(state["release"])
            self.fail(f"Unexpected mocked GitHub request: {method} {path}")
            return None

        return state, github

    def test_draft_pins_exact_tag_and_is_idempotent_without_publishing(self) -> None:
        """Remote tag/release writes are mocked; exact-commit Git guards are real."""
        assert hasattr(release, "create_draft"), (
            "Draft-only exact-source preparation is missing"
        )
        source = self.candidate()
        notes = '## Changes\n\n- Arbitrary " text\nEOF\n$(touch injected)\n'
        state, github = self.fake_github(source)
        with chdir(self.repo), mock.patch.object(release, "github", side_effect=github):
            url = release.create_draft(
                source,
                json.loads(self.event(source).read_text()),
                "fixture/product",
                notes,
            )
            assert url == state["release"]["html_url"]
            record = state["release"]
            assert record["target_commitish"] == source
            assert record["tag_name"] == "v3.0.1"
            assert record["name"] == "Release v3.0.1"
            assert record["draft"]
            assert not record["prerelease"]
            assert record["make_latest"] == "false"
            assert notes in record["body"]
            assert f"<!-- ai-shifu-release-source:{source} -->" in record["body"]
            assert [
                path.rsplit("/", 1)[-1]
                for method, path, _ in state["calls"]
                if method == "POST"
            ] == ["refs", "releases"]
            assert any(
                path.endswith("/releases/7")
                for method, path, _ in state["calls"]
                if method == "GET"
            )
            state["calls"].clear()
            record["body"] += "\nHuman note edits must survive reruns.\n"
            assert (
                release.create_draft(
                    source,
                    json.loads(self.event(source).read_text()),
                    "fixture/product",
                    "new notes",
                )
                == url
            )
            assert all(method == "GET" for method, _, _ in state["calls"])
            assert "Human note edits" in record["body"]
        assert not (self.repo / "injected").exists()
        assert self.git("tag") == "v3.0.0", (
            "Mocked remote writes must not touch local tags"
        )

    def release_record(self, source: str, *, draft: bool = True) -> dict:
        return {
            "id": 7,
            "tag_name": "v3.0.1",
            "target_commitish": source,
            "name": "Release v3.0.1",
            "draft": draft,
            "prerelease": False,
            "body": f"<!-- ai-shifu-release-source:{source} -->\n\nNotes\n",
            "html_url": "https://github.com/fixture/product/releases/untagged-fixture",
        }

    def test_draft_conflicts_fail_before_any_mocked_write(self) -> None:
        """Conflicts must not mutate mocked refs or public/other-source releases."""
        source = self.candidate()
        for case in (
            "tag-conflict",
            "public",
            "target",
            "name",
            "prerelease",
            "marker",
            "duplicate-notes-marker",
        ):
            with self.subTest(case=case):
                record = self.release_record(source)
                notes = "Notes"
                if case == "public":
                    record["draft"] = False
                if case == "target":
                    record["target_commitish"] = "main"
                if case == "name":
                    record["name"] = "Release v3.0.0"
                if case == "prerelease":
                    record["prerelease"] = True
                if case == "marker":
                    record["body"] = f"<!-- ai-shifu-release-source:{self.base} -->"
                if case == "duplicate-notes-marker":
                    notes = f"<!-- ai-shifu-release-source:{self.base} -->"
                state, github = self.fake_github(
                    source,
                    tag_sha=self.base if case == "tag-conflict" else source,
                    record=None
                    if case in {"tag-conflict", "duplicate-notes-marker"}
                    else record,
                )
                with (
                    chdir(self.repo),
                    mock.patch.object(release, "github", side_effect=github),
                    self.assertRaises(ValueError),
                ):
                    release.create_draft(
                        source,
                        json.loads(self.event(source).read_text()),
                        "fixture/product",
                        notes,
                    )
                assert all(method == "GET" for method, _, _ in state["calls"]), case

    def test_new_draft_verifies_notes_readback_and_reuses_orphan_same_source_tag(
        self,
    ) -> None:
        """Mocked GitHub write success alone is not acceptance of the draft contents."""
        source = self.candidate()
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                state, api = self.fake_github(source, tag_sha=source)

                def github(
                    method: str,
                    path: str,
                    payload: dict | None = None,
                    *,
                    missing_ok: bool = False,
                    api: object = api,
                    corrupt: bool = corrupt,
                ) -> object:
                    result = api(method, path, payload, missing_ok=missing_ok)
                    if corrupt and method == "GET" and path.endswith("/releases/7"):
                        result["body"] = (
                            f"<!-- ai-shifu-release-source:{source} -->\n\nMissing generated notes"
                        )
                    return result

                with (
                    chdir(self.repo),
                    mock.patch.object(release, "github", side_effect=github),
                ):
                    if corrupt:
                        with self.assertRaises(ValueError):
                            release.create_draft(
                                source,
                                json.loads(self.event(source).read_text()),
                                "fixture/product",
                                "Important notes",
                            )
                    else:
                        release.create_draft(
                            source,
                            json.loads(self.event(source).read_text()),
                            "fixture/product",
                            "Important notes",
                        )
                writes = [path for method, path, _ in state["calls"] if method != "GET"]
                assert writes == ["repos/fixture/product/releases"]

    def test_published_release_validates_source_before_any_build_or_write(self) -> None:
        """GitHub read responses are mocked; no registry or GitHub write is permitted."""
        assert hasattr(release, "validate_published"), (
            "Published release source guard is missing"
        )
        source = self.candidate()
        for case in (
            "valid",
            "draft",
            "prerelease",
            "tag",
            "target",
            "old-source",
            "remote-tag",
            "remote-publication",
            "automation",
            "wrong-action",
        ):
            with self.subTest(case=case):
                record = self.release_record(source, draft=False)
                if case == "draft":
                    record["draft"] = True
                if case == "prerelease":
                    record["prerelease"] = True
                if case == "tag":
                    record["tag_name"] = "v3.0.1$(touch injected)"
                if case == "target":
                    record["target_commitish"] = "main"
                state, api = self.fake_github(
                    source,
                    tag_sha=self.base if case == "remote-tag" else source,
                    record=record,
                )
                if case == "remote-publication":
                    state["release"] = {**record, "draft": True}
                if case == "automation":
                    state["pr"]["merged_by"]["login"] = "ai-shifu-bot"
                event = {
                    "action": "edited" if case == "wrong-action" else "published",
                    "release": record,
                }
                with (
                    chdir(self.repo),
                    mock.patch.object(release, "github", side_effect=api),
                ):
                    if case in {"draft", "prerelease"}:
                        values = release.validate_published(
                            source, event, "fixture/product"
                        )
                        assert values["should_build"] == "false"
                    elif case == "valid":
                        values = release.validate_published(
                            source, event, "fixture/product"
                        )
                        assert values == {
                            "should_build": "true",
                            "is_prerelease": "false",
                            "tag": "v3.0.1",
                            "version": "3.0.1",
                            "commit": source,
                        }
                    else:
                        with self.assertRaises(ValueError):
                            release.validate_published(
                                self.base if case == "old-source" else source,
                                event,
                                "fixture/product",
                            )
                assert all(method == "GET" for method, _, _ in state["calls"])

    def test_workflows_gate_drafts_and_pin_published_build_source(self) -> None:
        draft_path = ROOT / ".github/workflows/draft-release.yml"
        assert draft_path.exists(), "Automatic post-merge draft workflow is missing"
        draft = yaml.safe_load(draft_path.read_text())
        assert draft[True] == {"push": {"branches": ["main"]}}
        job = draft["jobs"]["draft"]
        checkout = next(
            step for step in job["steps"] if "actions/checkout" in step.get("uses", "")
        )
        assert checkout["with"]["ref"] == "${{ github.sha }}"
        assert checkout["with"]["fetch-depth"] == 0
        steps = {step.get("id"): step for step in job["steps"] if step.get("id")}
        assert '"$GITHUB_SHA"' in steps["source"]["run"]
        assert '"$GITHUB_EVENT_PATH"' in steps["source"]["run"]
        assert "create_draft == 'true'" in steps["release"]["if"]
        assert " draft " in steps["release"]["run"]
        published = yaml.safe_load(
            (ROOT / ".github/workflows/build-on-release.yml").read_text()
        )
        assert published[True] == {"release": {"types": ["published"]}}
        validation = published["jobs"]["validate-release"]
        step = next(step for step in validation["steps"] if step.get("id") == "extract")
        assert "validate-published" in step["run"]
        assert "${{" not in step["run"]
        build = published["jobs"]["build-docker"]
        assert build["needs"] == "validate-release"
        assert (
            build["with"]["source-ref"]
            == "${{ needs.validate-release.outputs.commit }}"
        )
        assert "needs.validate-release.outputs.commit" in build["with"]["labels"]
        reusable = yaml.safe_load(
            (ROOT / ".github/workflows/build-docker-image.yml").read_text()
        )
        assert reusable[True]["workflow_call"]["inputs"]["source-ref"]["default"] == ""
        for reusable_job in reusable["jobs"].values():
            checked = next(
                step
                for step in reusable_job["steps"]
                if "actions/checkout" in step.get("uses", "")
            )
            assert checked["with"]["ref"] == "${{ inputs.source-ref }}"
        static = yaml.safe_load(
            (ROOT / ".github/workflows/repo-harness.yml").read_text()
        )
        discovered = set()
        for job in static["jobs"].values():
            for static_step in job["steps"]:
                for command in static_step.get("run", "").splitlines():
                    if "unittest" not in command:
                        continue
                    arguments = shlex.split(command)
                    if arguments[1:4] != ["-m", "unittest", "discover"]:
                        continue
                    directory = ROOT / arguments[arguments.index("-s") + 1]
                    pattern = arguments[arguments.index("-p") + 1]
                    discovered.update(path.name for path in directory.glob(pattern))
        expected = {path.name for path in (ROOT / "scripts").glob("test_release_*.py")}
        assert expected <= discovered
        output = self.root / "published-output"
        event = self.root / "published.json"
        event.write_text(
            json.dumps(
                {"action": "published", "release": {"draft": True, "prerelease": False}}
            )
        )
        result = subprocess.run(
            [
                "bash",
                "-euo",
                "pipefail",
                "-c",
                step["run"].replace("scripts/release_workflow.py", str(SCRIPT)),
            ],
            cwd=self.repo,
            env={
                **os.environ,
                "GITHUB_EVENT_NAME": "release",
                "GITHUB_SHA": self.base,
                "GITHUB_EVENT_PATH": str(event),
                "GITHUB_OUTPUT": str(output),
                "GITHUB_REPOSITORY": "fixture/product",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "should_build=false\n" in output.read_text()

    def test_notes_cli_covers_all_commits_at_frozen_boundary_with_safe_file_io(
        self,
    ) -> None:
        """Run the actual notes CLI; only external Commitizen/HTTP lookups are mocked."""
        notes_script = ROOT / "scripts/release_notes.py"
        assert notes_script.exists(), "Frozen-source release notes CLI is missing"
        self.write("README.md", "# Fixture\n\n- Baseline note\n")
        self.write("changed.txt", "feature\n")
        self.commit('feat: support quoted " values (#20)')
        self.write("changed.txt", "ci\n")
        self.commit("ci: keep all PR coverage (#21)")
        source = self.candidate()
        self.git("tag", "v3.0.1", source)
        self.write("changed.txt", "later\n")
        self.commit("feat: do not leak newer main (#999)")
        self.git("tag", "v9.0.0")
        original_run = subprocess.run
        for cz_success in (False, True):
            with self.subTest(cz_success=cz_success):
                output = self.root / f"notes-{cz_success}.md"
                cz_calls = []

                def run(
                    arguments: list[str],
                    cz_calls: list = cz_calls,
                    cz_success: bool = cz_success,
                    **kwargs: object,
                ) -> subprocess.CompletedProcess[str]:
                    if arguments[0] == "cz":
                        cz_calls.append(arguments)
                        return subprocess.CompletedProcess(
                            arguments,
                            0 if cz_success else 1,
                            "## Unreleased\n\n### Feat\n\n- support quoted values (#20)\n"
                            if cz_success
                            else "",
                            "",
                        )
                    return original_run(arguments, **kwargs)

                argv = [
                    str(notes_script),
                    "--source",
                    source,
                    "--version",
                    "3.0.1",
                    "--repository",
                    "fixture/product",
                    "--output",
                    str(output),
                ]
                with (
                    chdir(self.repo),
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.object(subprocess, "run", side_effect=run),
                    mock.patch.object(
                        urllib.request,
                        "urlopen",
                        side_effect=OSError("mocked lookup unavailable"),
                    ),
                ):
                    runpy.run_path(str(notes_script), run_name="__main__")
                notes = output.read_text()
                assert "(#20)" in notes
                assert "(#21)" in notes
                assert "(#2)" in notes
                assert "(#999)" not in notes
                assert "Baseline note" not in notes
                assert "## Unreleased" not in notes
                assert "Installation from Source" in notes
                assert "Upgrading to numbered models" in notes
                assert source in notes
                assert cz_calls == [
                    ["cz", "changelog", "--dry-run", "--start-rev", "v3.0.0"]
                ]
                assert not (self.repo / "CHANGELOG.md").exists()

    def test_notes_do_not_duplicate_rendered_conventional_subjects_without_pr(
        self,
    ) -> None:
        """Use real Git subjects; mock only successful Commitizen and author HTTP."""
        covered = {
            "feat: add login": "add login",
            "fix(auth): retain sessions": "**auth**: retain sessions",
            "feat!: remove legacy login": "remove legacy login",
            "feat(api)!: require login tokens": "**api**: require login tokens",
        }
        omitted = ("chore: refresh build tooling", "Document upgrade checklist")
        for subject in (*covered, *omitted):
            self.write("changed.txt", subject + "\n")
            self.commit(subject)
        source = self.candidate()
        self.write("changed.txt", "later\n")
        self.commit("feat: exclude newer login changes")
        original_run = subprocess.run
        cz_calls = []

        def run(
            arguments: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if arguments[0] == "cz":
                cz_calls.append(arguments)
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    "## Unreleased\n\n### Feat\n\n"
                    "- **api**: require login tokens\n"
                    "- remove legacy login\n"
                    "- add login\n\n### Fix\n\n"
                    "- **auth**: retain sessions\n",
                    "",
                )
            return original_run(arguments, **kwargs)

        with (
            chdir(self.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
            mock.patch.object(subprocess, "run", side_effect=run),
            mock.patch.object(
                urllib.request,
                "urlopen",
                return_value=io.BytesIO(b'{"user": {"login": "fixture-teacher"}}'),
            ),
        ):
            rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
        assert cz_calls == [["cz", "changelog", "--dry-run", "--start-rev", "v3.0.0"]]
        assert "### Other Changes" in rendered
        for subject in omitted:
            assert f"- {subject}" in rendered
        assert "(#2) (@fixture-teacher)" in rendered
        assert "exclude newer login changes" not in rendered
        for subject, body in covered.items():
            with self.subTest(subject=subject):
                assert f"- {body}" in rendered
                assert f"- {subject}" not in rendered, rendered

    def test_notes_retain_omitted_subjects_overlapping_a_longer_rendered_entry(
        self,
    ) -> None:
        """A rendered feature must not hide shorter maintenance or plain Git subjects."""
        feature = "feat: add build tooling diagnostics"
        omitted = ("chore: build tooling", "build tooling")
        for subject in (feature, *omitted):
            self.write("changed.txt", subject + "\n")
            self.commit(subject)
        source = self.git("rev-parse", "HEAD")
        original_run = subprocess.run

        def run(
            arguments: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if arguments[0] == "cz":
                assert arguments == [
                    "cz",
                    "changelog",
                    "--dry-run",
                    "--start-rev",
                    "v3.0.0",
                ]
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    "## Unreleased\n\n### Feat\n\n- add build tooling diagnostics\n",
                    "",
                )
            return original_run(arguments, **kwargs)

        with (
            chdir(self.repo),
            mock.patch.object(subprocess, "run", side_effect=run),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("No PR author lookup is needed"),
            ),
        ):
            rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
        for subject in omitted:
            with self.subTest(subject=subject):
                assert f"- {subject}" in rendered.splitlines(), rendered
        assert rendered.count("- add build tooling diagnostics") == 1
        assert f"- {feature}" not in rendered.splitlines()

    def test_notes_do_not_confuse_omitted_subjects_with_other_change_categories(
        self,
    ) -> None:
        """Identical descriptions in features/fixes do not cover maintenance or plain commits."""
        covered = {
            "feat: build tooling": "build tooling",
            "fix(auth): retain sessions": "**auth**: retain sessions",
            "feat(api)!: require login tokens": "**api**: require login tokens",
        }
        omitted = (
            "chore: build tooling",
            "build tooling",
            "chore(auth): retain sessions",
            "chore(api)!: require login tokens",
            "chore(other): retain sessions",
        )
        for subject in (*covered, *omitted):
            self.write("changed.txt", subject + "\n")
            self.commit(subject)
        source = self.git("rev-parse", "HEAD")
        original_run = subprocess.run

        def run(
            arguments: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if arguments[0] == "cz":
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    "## Unreleased\n\n### Feat\n\n"
                    "- **api**: require login tokens\n"
                    "- build tooling\n\n### Fix\n\n"
                    "- **auth**: retain sessions\n",
                    "",
                )
            return original_run(arguments, **kwargs)

        with (
            chdir(self.repo),
            mock.patch.object(subprocess, "run", side_effect=run),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("No PR author lookup is needed"),
            ),
        ):
            rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
        other_changes = rendered.partition("### Other Changes\n\n")[2].splitlines()
        for subject in omitted:
            with self.subTest(subject=subject):
                assert f"- {subject}" in other_changes, rendered
        for subject, body in covered.items():
            with self.subTest(covered=subject):
                assert f"- {body}" in rendered.splitlines()
                assert f"- {subject}" not in rendered.splitlines(), rendered

    def test_notes_ignore_non_entry_mentions_in_custom_changelogs(self) -> None:
        """Headings, prose, nested notes and unknown sections cannot hide Git changes."""
        feature = "feat: add diagnostics (#20)"
        omitted = (
            "feat: heading-only",
            "fix: prose-only",
            "feat: nested-only",
            "feat: custom-section-only",
            "chore: heading-only (#21)",
            "chore: prose-only (#22)",
            "chore: nested-only (#23)",
            "chore: custom-section-only (#24)",
        )
        for subject in (feature, *omitted):
            self.write("changed.txt", subject + "\n")
            self.commit(subject)
        source = self.git("rev-parse", "HEAD")
        original_run = subprocess.run

        def run(
            arguments: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if arguments[0] == "cz":
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    "## Unreleased\n\n### Feat\n\n- add diagnostics (#20)\n"
                    "  - nested-only\n  - nested-only (#23)\n\n"
                    "prose-only\nprose-only (#22)\n\n"
                    "#### heading-only (#21)\n\n"
                    "### Custom section\n\n"
                    "- custom-section-only\n- custom-section-only (#24)\n",
                    "",
                )
            return original_run(arguments, **kwargs)

        with (
            chdir(self.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
            mock.patch.object(subprocess, "run", side_effect=run),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=lambda *_args, **_kwargs: io.BytesIO(
                    b'{"user": {"login": "fixture-teacher"}}'
                ),
            ),
        ):
            rendered = notes.product_notes(source, "v3.0.0", "fixture/product")
        other_changes = rendered.partition("### Other Changes\n\n")[2].splitlines()
        for subject in omitted:
            with self.subTest(subject=subject):
                annotation = " (@fixture-teacher)" if "(#" in subject else ""
                assert f"- {subject}{annotation}" in other_changes, rendered
        assert "- add diagnostics (#20) (@fixture-teacher)" in rendered.splitlines()
        assert f"- {feature} (@fixture-teacher)" not in rendered.splitlines()

    def dependency_range(self) -> str:
        self.write("src/api/requirements.txt", "markdown-flow==1.0.0\n")
        self.git("rm", "src/web/package-lock.json")
        self.write(
            "src/" + "cook-web/package-lock.json",
            json.dumps(
                {"packages": {"node_modules/markdown-flow-ui": {"version": "1.0.0"}}}
            ),
        )
        baseline = self.commit("chore: historical dependency pins")
        self.git("tag", "-f", "v3.0.0", baseline)
        self.versions("3.0.1")
        self.write("src/api/requirements.txt", "markdown-flow==2.0.0\n")
        lock_path = self.repo / "src/web/package-lock.json"
        lock = json.loads(lock_path.read_text())
        lock["packages"]["node_modules/markdown-flow-ui"] = {"version": "2.0.0"}
        lock_path.write_text(json.dumps(lock))
        source = self.commit("chore: flow version to v3.0.1 (#2)")
        self.write("src/api/requirements.txt", "markdown-flow==9.0.0\n")
        lock["packages"]["node_modules/markdown-flow-ui"] = {"version": "9.0.0"}
        lock_path.write_text(json.dumps(lock))
        self.commit("chore: later dependency changes")
        return source

    def test_notes_preserve_frozen_dependency_tag_ranges_legacy_paths_and_authors(
        self,
    ) -> None:
        """Mock external APIs; read previous and candidate pins from actual Git objects."""
        source = self.dependency_range()
        urls = []

        def response(request: urllib.request.Request, timeout: int) -> io.BytesIO:
            assert timeout > 0
            url = request.full_url
            urls.append(url)
            if "/compare/" in url:
                data = {
                    "commits": [
                        {"commit": {"message": "chore: release 2.0.0"}},
                        {"commit": {"message": "fix: frozen dependency fix (#10)"}},
                        {
                            "commit": {
                                "message": "feat: frozen dependency feature (#11)"
                            }
                        },
                        {
                            "commit": {
                                "message": "feat: frozen dependency feature (#11)"
                            }
                        },
                    ]
                }
            elif "/pulls/" in url:
                data = {"user": {"login": "fixture-teacher"}}
            else:
                data = {"object": {"sha": source}}
            return io.BytesIO(json.dumps(data).encode())

        with (
            chdir(self.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
            mock.patch.object(urllib.request, "urlopen", side_effect=response),
        ):
            rendered = notes.generate_notes(source, "3.0.1", "fixture/product")
        assert "## MarkdownFlow Dependency Updates" in rendered
        for name in ("markdown-flow", "markdown-flow-ui"):
            assert f"`{name}` `1.0.0` -> `2.0.0`" in rendered
        assert "ai-shifu/markdown-flow-agent-py#10" in rendered
        assert "ai-shifu/markdown-flow-ui#11" in rendered
        assert "(@fixture-teacher)" in rendered
        assert "release 2.0.0" not in rendered
        assert "9.0.0" not in rendered
        assert rendered.count("frozen dependency feature") == 2
        assert rendered.index("frozen dependency feature") < rendered.index(
            "frozen dependency fix"
        )
        assert any("v1.0.0...v2.0.0" in url for url in urls)

    def test_dependency_registry_fallback_keeps_pagination_dedup_and_truncation(
        self,
    ) -> None:
        """No external network: simulate registry time windows and three API pages."""
        assert hasattr(notes, "dependency_notes"), (
            "Dependency note generation is missing"
        )
        source = self.dependency_range()
        pages = []

        def response(request: urllib.request.Request, timeout: int) -> io.BytesIO:
            assert timeout > 0
            url = request.full_url
            if "/git/ref/tags/" in url:
                raise urllib.error.HTTPError(url, 404, "Mocked absent tag", None, None)
            hostname = urllib.parse.urlsplit(url).hostname
            if hostname == "pypi.org":
                data = {
                    "releases": {
                        "1.0.0": [{"upload_time_iso_8601": "2026-01-01T00:00:00Z"}],
                        "2.0.0": [{"upload_time_iso_8601": "2026-02-01T00:00:00Z"}],
                    }
                }
            elif hostname == "registry.npmjs.org":
                data = {
                    "time": {
                        "1.0.0": "2026-01-01T00:00:00Z",
                        "2.0.0": "2026-02-01T00:00:00Z",
                    }
                }
            elif "/commits?" in url:
                assert "since=2026-01-01" in url
                assert "until=2026-02-01" in url
                page = int(url.rsplit("page=", 1)[1])
                pages.append(page)
                data = [
                    {
                        "commit": {
                            "message": "chore: release 2.0.0"
                            if i == 0
                            else f"feat: change {page}-{i}"
                        }
                    }
                    for i in range(100)
                ]
            else:
                self.fail(f"Unexpected mocked lookup: {url}")
            return io.BytesIO(json.dumps(data).encode())

        with (
            chdir(self.repo),
            mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
            mock.patch.object(urllib.request, "urlopen", side_effect=response),
        ):
            rendered = notes.dependency_notes("v3.0.0", source)
        assert pages == [1, 2, 3, 1, 2, 3]
        assert sum(line.startswith("- ") for line in rendered.splitlines()) == 40
        assert "...and 278 more commits" in rendered
        assert "release 2.0.0" not in rendered

    def test_annotated_remote_tag_is_peeled_to_the_exact_git_fixture_commit(
        self,
    ) -> None:
        """Use a real annotated Git tag; mock only GitHub object lookup responses."""
        source = self.candidate()
        self.git("tag", "-a", "v3.0.1", source, "-m", "Fixture formal tag")
        tag_object = self.git("rev-parse", "refs/tags/v3.0.1")
        assert tag_object != source

        def github(
            method: str,
            path: str,
            payload: dict | None = None,
            *,
            missing_ok: bool = False,
        ) -> object:
            assert method == "GET"
            assert payload is None
            if "/git/ref/" in path:
                assert missing_ok
                return {"object": {"type": "tag", "sha": tag_object}}
            assert path.endswith(f"/git/tags/{tag_object}")
            return {
                "object": {
                    "type": "commit",
                    "sha": self.git("rev-parse", "v3.0.1^{commit}"),
                }
            }

        with chdir(self.repo), mock.patch.object(release, "github", side_effect=github):
            try:
                actual = release.remote_tag("fixture/product", "v3.0.1")
            except ValueError as error:
                self.fail(
                    f"An existing same-source annotated tag must be reusable: {error}"
                )
            assert actual == source

    def test_harness_legacy_exception_follows_only_dependency_metadata(self) -> None:
        import check_repo_harness as harness

        owner = Path("scripts/release_notes.py")
        assert owner in harness.STALE_FRONTEND_PATH_LINE_ALLOWLIST
        assert (
            Path(".github/workflows/prepare-release.yml")
            not in harness.STALE_FRONTEND_PATH_LINE_ALLOWLIST
        )
        lines = (ROOT / owner).read_text().splitlines()
        occurrence = next(
            index + 1 for index, line in enumerate(lines) if '"legacy_path":' in line
        )
        assert harness._stale_path_is_in_allowed_context(owner, lines, [occurrence])
        lines.append(lines[occurrence - 1])
        assert not harness._stale_path_is_in_allowed_context(owner, lines, [len(lines)])

    def test_preparation_keeps_notes_preview_in_a_file_with_manual_merge_handoff(
        self,
    ) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/prepare-release.yml").read_text()
        )
        job = workflow["jobs"]["prepare"]
        pr = next(
            step
            for step in job["steps"]
            if "create-pull-request" in step.get("uses", "")
        )
        assert pr["with"].get("body-path") == "${{ runner.temp }}/release-pr.md", (
            "Notes preview must travel as a file"
        )
        step = next(step for step in job["steps"] if "--pr-body" in step.get("run", ""))
        assert "${{" not in step["run"]
        body = self.root / "release-pr.md"
        event_source = self.base
        script = step["run"].replace(
            "scripts/release_notes.py", str(ROOT / "scripts/release_notes.py")
        )
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", script],
            cwd=self.repo,
            env={
                **os.environ,
                "GH_TOKEN": "",
                "GITHUB_TOKEN": "",
                "RELEASE_TOKEN": "",
                "GITHUB_SHA": event_source,
                "GITHUB_REPOSITORY": "fixture/product",
                "RELEASE_VERSION": "3.0.1",
                "RUNNER_TEMP": str(self.root),
            },
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        content = body.read_text()
        assert "manually merge" in content
        assert "Never enable auto-merge" in content
        assert "manually Publish" in content
        assert "Changelog preview" in content
        assert "Installation from Source" in content
        assert self.git("tag") == "v3.0.0"

    def test_draft_cli_runs_real_transport_with_only_http_writes_mocked(self) -> None:
        """Execute the real CLI and REST JSON transport; all HTTP is mocked explicitly."""
        source = self.candidate()
        event = self.event(source)
        note_file = self.root / "input-notes.md"
        note_file.write_text("## Notes\nEOF\nurl=injected\n$(touch injected)\n")
        for malicious_url in (False, True):
            with self.subTest(malicious_url=malicious_url):
                state, api = self.fake_github(source)
                output = self.root / f"cli-output-{malicious_url}"

                def response(
                    request: urllib.request.Request,
                    timeout: int,
                    api: object = api,
                    malicious_url: bool = malicious_url,
                ) -> io.BytesIO:
                    assert timeout == 30
                    path = request.full_url.removeprefix("https://api.github.com/")
                    payload = json.loads(request.data) if request.data else None
                    record = api(
                        request.get_method(),
                        path,
                        payload,
                        missing_ok="/git/ref/" in path,
                    )
                    if malicious_url and path.endswith("/releases/7"):
                        record["html_url"] += "\ntag=injected"
                    if record is None:
                        raise urllib.error.HTTPError(
                            request.full_url, 404, "mock absent", None, None
                        )
                    return io.BytesIO(json.dumps(record).encode())

                argv = [
                    str(SCRIPT),
                    "draft",
                    "--source",
                    source,
                    "--event",
                    str(event),
                    "--repository",
                    "fixture/product",
                    "--notes",
                    str(note_file),
                    "--output",
                    str(output),
                ]
                with (
                    chdir(self.repo),
                    mock.patch.object(sys, "argv", argv),
                    mock.patch.dict(os.environ, {"GH_TOKEN": "fixture-credential"}),
                    mock.patch.object(urllib.request, "urlopen", side_effect=response),
                ):
                    if malicious_url:
                        with self.assertRaises(SystemExit):
                            runpy.run_path(str(SCRIPT), run_name="__main__")
                        assert not output.exists()
                    else:
                        runpy.run_path(str(SCRIPT), run_name="__main__")
                        assert output.read_text().splitlines() == [
                            "url=" + state["release"]["html_url"]
                        ]
                assert not (self.repo / "injected").exists()

    def test_initial_notes_keep_readme_feature_section_without_network(self) -> None:
        self.git("tag", "-d", "v3.0.0")
        self.write(
            "README.md",
            "# Fixture\n\nA fixture description.\n\n# Features\n\n- Initial feature coverage\n\n# Support\n\nOther text\n",
        )
        source = self.commit("feat: initial notes fixture")
        with (
            chdir(self.repo),
            mock.patch.object(
                urllib.request,
                "urlopen",
                side_effect=AssertionError("No initial-note network"),
            ),
        ):
            rendered = notes.generate_notes(source, "3.0.1", "fixture/product")
        assert "Initial feature coverage" in rendered
        assert "A fixture description" in rendered
        assert "# Features" in rendered

    def test_prepare_workflow_is_pr_only_with_injection_safe_handoff(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/prepare-release.yml").read_text()
        )
        text = str(workflow)
        assert "action-gh-release" not in text
        assert "gh release" not in text
        job = workflow["jobs"]["prepare"]
        assert job["if"] == "github.ref == 'refs/heads/main'"
        step = next(step for step in job["steps"] if step.get("id") == "version")
        assert step["env"]["RELEASE_TAG"] == "${{ inputs.version }}"
        assert "${{" not in step["run"]
        pr = next(
            step
            for step in job["steps"]
            if "create-pull-request" in step.get("uses", "")
        )
        assert pr["with"]["base"] == "main"
        assert pr["with"]["body-path"] == "${{ runner.temp }}/release-pr.md"
        assert "enable-pull-request-automerge" not in text
        assert "gh pr merge" not in text
        output = self.root / "output"
        marker = self.repo / "injected"
        result = subprocess.run(
            [
                "bash",
                "-euo",
                "pipefail",
                "-c",
                step["run"].replace("scripts/release_workflow.py", str(SCRIPT)),
            ],
            cwd=self.repo,
            env={
                **os.environ,
                "RELEASE_TAG": "v3.0.1$(touch injected)",
                "GITHUB_SHA": self.base,
                "GITHUB_OUTPUT": str(output),
            },
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert not marker.exists()
        assert not output.exists()
        assert self.git("diff") == ""

    def test_prepare_updates_owned_versions_without_creating_tags(self) -> None:
        latest_before = (self.repo / "docker/docker-compose.latest.yml").read_bytes()
        result = self.invoke("prepare", "--tag=v3.0.1", "--source", self.base)
        assert result.returncode == 0, result.stderr
        for package in PACKAGES:
            manifest = json.loads((self.repo / package / "package.json").read_text())
            lock = json.loads((self.repo / package / "package-lock.json").read_text())
            assert manifest["version"] == "3.0.1"
            assert manifest["dependencies"] == {"unchanged": "1.2.3"}
            assert lock["version"] == "3.0.1"
            assert lock["packages"][""]["version"] == "3.0.1"
            assert lock["packages"]["node_modules/unchanged"]["version"] == "1.2.3"
        assert '__version__ = "3.0.1"' in (self.repo / ENGINE).read_text()
        pinned = (self.repo / "docker/docker-compose.yml").read_text()
        assert "aishifu/ai-shifu-web:v3.0.1" in pinned
        assert "aishifu/ai-shifu-api:v3.0.1" in pinned
        assert "redis:7-alpine" in pinned
        assert (
            self.repo / "docker/docker-compose.latest.yml"
        ).read_bytes() == latest_before
        assert self.git("tag") == "v3.0.0"
        assert self.git("rev-parse", "HEAD") == self.base


if __name__ == "__main__":
    unittest.main()
