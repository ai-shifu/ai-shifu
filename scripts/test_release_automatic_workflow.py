# ruff: noqa: INP001 -- Standalone workflow regressions are discovered by path.
"""Exercise automatic release routing, publication gates, and pinned shell inputs."""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_release_workflow as fixtures
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_workflow.py"
SOURCE = "1" * 40
NEWER = "2" * 40


def load_workflow(name: str) -> dict:
    """Read the committed automation surface instead of a duplicated test fixture."""
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def evaluate(expression: str, context: dict) -> object:
    """Interpret the small Actions expression subset used by release job gates."""
    expression = expression.strip().removeprefix("${{").removesuffix("}}").strip()
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = re.sub(r"!(?!=)", "not ", expression).strip()
    expression = expression.replace(".build-images", ".build_images")
    tree = ast.parse(expression, mode="eval")

    def interpret(node: ast.AST) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return {"true": True, "false": False, **context}[node.id]
        if isinstance(node, ast.Attribute):
            return interpret(node.value)[node.attr]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not interpret(node.operand)
        if isinstance(node, ast.BoolOp):
            value = interpret(node.values[0])
            for following in node.values[1:]:
                if isinstance(node.op, ast.And) and not value:
                    return value
                if isinstance(node.op, ast.Or) and value:
                    return value
                value = interpret(following)
            return value
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left = interpret(node.left)
            right = interpret(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            if isinstance(node.ops[0], ast.NotEq):
                return left != right
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "cancelled"
            and not node.args
            and not node.keywords
        ):
            return context["cancelled"]
        message = f"Unsupported release workflow expression: {ast.dump(node)}"
        raise ValueError(message)

    return interpret(tree.body)


def job_eligible(job: dict, context: dict) -> bool:
    """Include Actions' implicit success gate unless an explicit status test replaces it."""
    condition = job.get("if", "true")
    needs = job.get("needs", [])
    if isinstance(needs, str):
        needs = [needs]
    if not re.search(r"\b(?:cancelled|always|failure|success)\(", condition) and any(
        context["needs"][name.replace("-", "_")]["result"] != "success"
        for name in needs
    ):
        return False
    return bool(evaluate(condition, context))


def release_context(
    *,
    draft: str = "success",
    images: str = "success",
    create: str = "true",
    build: str = "true",
    cancelled: bool = False,
) -> dict:
    """Describe upstream results independently of the workflow's eligibility expression."""
    return {
        "cancelled": cancelled,
        "needs": {
            "draft": {
                "result": draft,
                "outputs": {"create_draft": create, "should_build": build},
            },
            "build_images": {"result": images},
        },
    }


class AutomaticReleaseWorkflowTests(unittest.TestCase):
    """Run real workflow scripts and assert release ordering and trust boundaries."""

    def setUp(self) -> None:
        self.workflow = load_workflow("draft-release.yml")
        self.images = load_workflow("build-on-release.yml")
        self.jobs = self.workflow["jobs"]
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def step(self, job: dict, identifier: str) -> dict:
        """Select the operation step whose arguments form the public CLI integration."""
        return next(step for step in job["steps"] if step.get("id") == identifier)

    def shell(
        self, script: str, **environment: str
    ) -> subprocess.CompletedProcess[str]:
        """Execute an actual workflow run block with the runner's fail-fast Bash flags."""
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
            cwd=self.directory,
            env={**os.environ, **environment},
            capture_output=True,
            text=True,
            check=False,
        )

    def run_stubbed(
        self, step: dict, *, event: str, status: int = 0
    ) -> tuple[int, list]:
        """Capture CLI routing without executing GitHub writes or image publication."""
        binary = self.directory / "bin"
        binary.mkdir(exist_ok=True)
        python = binary / "python"
        python.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "with Path(os.environ['CAPTURE']).open('a') as output:\n"
            "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "sys.exit(int(os.environ['STUB_STATUS']))\n"
        )
        python.chmod(0o755)
        capture = self.directory / "calls.jsonl"
        capture.write_text("")
        event_path = self.directory / "event.json"
        event_path.write_text(json.dumps({"inputs": {"expected_version": "3.0.1"}}))
        result = self.shell(
            step["run"],
            PATH=f"{binary}{os.pathsep}{os.environ['PATH']}",
            CAPTURE=str(capture),
            STUB_STATUS=str(status),
            GITHUB_EVENT_NAME=event,
            GITHUB_EVENT_PATH=str(event_path),
            GITHUB_OUTPUT=str(self.directory / "outputs"),
            GITHUB_REPOSITORY="fixture/product",
            RUNNER_TEMP=str(self.directory),
            RELEASE_SOURCE=SOURCE,
            RELEASE_TAG="v3.0.1",
            RELEASE_VERSION="3.0.1",
        )
        calls = [json.loads(line) for line in capture.read_text().splitlines()]
        return result.returncode, calls

    def test_staging_is_main_only_with_explicit_original_source_recovery(self) -> None:
        assert self.workflow[True]["push"] == {"branches": ["main"]}
        inputs = self.workflow[True]["workflow_dispatch"]["inputs"]
        assert set(inputs) == {"source_commit", "expected_version"}
        assert all(
            field["required"] and field["type"] == "string" for field in inputs.values()
        )
        context = {"github": {"ref": "refs/heads/main"}}
        assert job_eligible(self.jobs["draft"], context)
        context["github"]["ref"] = "refs/heads/feature"
        assert not job_eligible(self.jobs["draft"], context)
        selection = self.step(self.jobs["draft"], "source")
        context = {"inputs": {"source_commit": SOURCE}, "github": {"sha": NEWER}}
        assert evaluate(selection["env"]["RELEASE_SOURCE"], context) == SOURCE
        context["inputs"]["source_commit"] = ""
        assert evaluate(selection["env"]["RELEASE_SOURCE"], context) == NEWER

    def test_publication_requires_successful_images_or_verified_public_retry(
        self,
    ) -> None:
        assert set(self.jobs["publish"]["needs"]) == {"draft", "build-images"}
        cases = (
            ({}, True),
            ({"images": "failure"}, False),
            ({"images": "cancelled"}, False),
            ({"images": "skipped"}, False),
            ({"draft": "failure"}, False),
            ({"draft": "cancelled"}, False),
            ({"draft": "skipped"}, False),
            ({"cancelled": True}, False),
            ({"create": "false", "images": "skipped"}, False),
            ({"build": "false", "images": "skipped"}, True),
            ({"build": "false", "images": "failure"}, False),
            ({"build": "false", "images": "cancelled"}, False),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                assert (
                    job_eligible(self.jobs["publish"], release_context(**changes))
                    is expected
                )
        assert not job_eligible(
            self.jobs["build-images"], release_context(build="false", images="skipped")
        )
        assert not job_eligible(
            self.jobs["build-images"], release_context(draft="failure")
        )

    def test_both_services_reuse_native_smoke_and_manifest_verification(self) -> None:
        images = self.jobs["build-images"]
        assert images["uses"] == "./.github/workflows/build-on-release.yml"
        assert images["needs"] == "draft"
        assert images["with"] == {
            "source_commit": "${{ needs.draft.outputs.commit }}",
            "tag": "${{ needs.draft.outputs.tag }}",
        }
        build = self.images["jobs"]["build-docker"]
        assert {
            entry["service"] for entry in build["strategy"]["matrix"]["include"]
        } == {"api", "web"}
        assert build["uses"] == "./.github/workflows/build-docker-image.yml"
        assert (
            build["with"]["source-ref"]
            == "${{ needs.validate-release.outputs.commit }}"
        )
        native = load_workflow("build-docker-image.yml")
        assert json.loads(
            native[True]["workflow_call"]["inputs"]["architectures"]["default"]
        ) == ["amd64", "arm64"]
        assert "architectures" not in build["with"]
        steps = [step["name"] for step in native["jobs"]["build"]["steps"]]
        assert steps.index("Smoke-test production image") < steps.index(
            "Push tested native image by digest"
        )
        assert steps.index("Push tested native image by digest") < steps.index(
            "Verify pushed content matches production smoke"
        )
        manifest = native["jobs"]["publish"]
        assert manifest["needs"] == "build"
        assert any(
            "scripts/merge_docker_manifests.py" in step.get("run", "")
            for step in manifest["steps"]
        )
        assert (
            build["with"]["tags"].strip()
            == "type=raw,value=${{ needs.validate-release.outputs.tag }}"
        )
        assert "latest" not in build["with"]["tags"]

    def test_runtime_checkouts_are_trusted_and_pat_is_limited_to_mutations(
        self,
    ) -> None:
        jobs = [
            self.jobs["draft"],
            self.jobs["publish"],
            self.images["jobs"]["validate-release"],
        ]
        for job in jobs:
            checkout = next(
                step
                for step in job["steps"]
                if "actions/checkout" in step.get("uses", "")
            )
            assert checkout["with"]["ref"] == "${{ github.workflow_sha }}"
            assert checkout["with"]["persist-credentials"] is False
        privileged = [
            (job_name, step.get("id"))
            for job_name, job in self.jobs.items()
            for step in job.get("steps", [])
            if "secrets.PAT_TOKEN" in str(step)
        ]
        assert privileged == [("draft", "release"), ("publish", "publication")]
        notes = next(
            step
            for step in self.jobs["draft"]["steps"]
            if "scripts/release_notes.py" in step.get("run", "")
        )
        assert notes["env"]["GH_TOKEN"] == "${{ github.token }}"  # noqa: S105 -- Literal Actions expression, not a credential.
        validation = self.step(self.images["jobs"]["validate-release"], "extract")
        assert validation["env"]["GH_TOKEN"] == notes["env"]["GH_TOKEN"]
        assert "secrets.PAT_TOKEN" not in str(self.images)
        for workflow in (self.workflow, self.images):
            for job in workflow["jobs"].values():
                for step in job.get("steps", []):
                    assert "${{ inputs." not in step.get("run", "")

    def test_image_validation_routes_real_event_context_and_preserves_source(
        self,
    ) -> None:
        step = self.step(self.images["jobs"]["validate-release"], "extract")
        assert self.images[True]["release"] == {"types": ["published"]}
        assert set(self.images[True]["workflow_call"]["inputs"]) == {
            "source_commit",
            "tag",
        }
        for event in ("push", "workflow_dispatch", "release"):
            with self.subTest(event=event):
                status, calls = self.run_stubbed(step, event=event)
                assert status == 0
                assert len(calls) == 1
                arguments = calls[0]
                assert arguments[0] == "scripts/release_workflow.py"
                assert arguments[1] == (
                    "validate-published" if event == "release" else "validate-candidate"
                )
                assert arguments[arguments.index("--source") + 1] == SOURCE
                assert (
                    arguments[arguments.index("--repository") + 1] == "fixture/product"
                )
                if event == "release":
                    assert "--event" in arguments
                    assert "--tag" not in arguments
                else:
                    assert arguments[arguments.index("--tag") + 1] == "v3.0.1"
                    assert "--event" not in arguments

    def test_image_validation_failure_is_not_reported_as_success(self) -> None:
        step = self.step(self.images["jobs"]["validate-release"], "extract")
        for event in ("push", "workflow_dispatch", "release"):
            with self.subTest(event=event):
                status, calls = self.run_stubbed(step, event=event, status=37)
                assert status == 37
                assert len(calls) == 1

    def test_staging_and_publication_use_the_same_source_and_propagate_failure(
        self,
    ) -> None:
        stages = (("draft", "release", "stage"), ("publish", "publication", "publish"))
        for job, identifier, command in stages:
            step = self.step(self.jobs[job], identifier)
            with self.subTest(command=command):
                status, calls = self.run_stubbed(step, event="push", status=29)
                assert status == 29
                assert len(calls) == 1
                arguments = calls[0]
                assert arguments[1] == command
                assert arguments[arguments.index("--source") + 1] == SOURCE
                if command == "publish":
                    assert arguments[arguments.index("--tag") + 1] == "v3.0.1"

    def test_manual_selection_executes_the_real_original_commit_guard(self) -> None:
        fixture = fixtures.ReleaseFixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.write("scripts/release_workflow.py", "AUTOMATIC_RELEASE_PROTOCOL = 1\n")
        source = fixture.candidate()
        fixture.write("README.md", "# A later main commit\n")
        newer = fixture.commit("docs: advance main after the version merge")
        fixture.git("update-ref", "refs/remotes/origin/main", newer)
        selection = self.step(self.jobs["draft"], "source")
        script = selection["run"].replace(
            "python scripts/release_workflow.py",
            f"{shlex.quote(sys.executable)} {shlex.quote(str(SCRIPT))}",
        )
        cases = (
            (source, "3.0.1", "refs/heads/main", True),
            (source[:-1], "3.0.1", "refs/heads/main", False),
            (source, "3.0.2", "refs/heads/main", False),
            (source, "", "refs/heads/main", False),
            (source, "3.0.1", "refs/heads/feature", False),
        )
        for candidate, version, ref, expected in cases:
            with self.subTest(candidate=candidate, version=version, ref=ref):
                event = fixture.root / "manual-event.json"
                event.write_text(
                    json.dumps(
                        {
                            "inputs": {
                                "source_commit": candidate,
                                "expected_version": version,
                            }
                        }
                    )
                )
                output = fixture.root / "manual-output"
                output.unlink(missing_ok=True)
                result = subprocess.run(
                    ["bash", "-e", "-o", "pipefail", "-c", script],
                    cwd=fixture.repo,
                    env={
                        **os.environ,
                        "GITHUB_EVENT_NAME": "workflow_dispatch",
                        "GITHUB_REF": ref,
                        "GITHUB_EVENT_PATH": str(event),
                        "GITHUB_OUTPUT": str(output),
                        "RELEASE_SOURCE": candidate,
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert (result.returncode == 0) is expected, result.stderr
                if expected:
                    values = dict(
                        line.split("=", 1) for line in output.read_text().splitlines()
                    )
                    assert values["commit"] == source
                    assert values["create_draft"] == "true"
                else:
                    assert not output.exists()


class DraftVisibilityTests(unittest.TestCase):
    """Draft metadata lookups require a push-capable repository token."""

    def test_only_candidate_validation_needs_write_access_to_read_drafts(self) -> None:
        """The caller must permit draft visibility without elevating image builders."""
        coordinator = yaml.safe_load(
            (ROOT / ".github/workflows/draft-release.yml").read_text()
        )
        images = yaml.safe_load(
            (ROOT / ".github/workflows/build-on-release.yml").read_text()
        )
        assert coordinator["jobs"]["build-images"]["permissions"]["contents"] == "write"
        assert images["jobs"]["validate-release"]["permissions"] == {
            "contents": "write",
            "pull-requests": "read",
        }
        assert images["jobs"]["build-docker"]["permissions"]["contents"] == "read"
        validation = next(
            step
            for step in images["jobs"]["validate-release"]["steps"]
            if step.get("id") == "extract"
        )
        assert validation["env"]["GH_TOKEN"] == "${{ github.token }}"  # noqa: S105 -- Workflow expression, not a credential.


if __name__ == "__main__":
    unittest.main()
