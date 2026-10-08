# ruff: noqa: INP001 -- This test is a standalone repository script.
"""Protect production image coverage while avoiding duplicate PR image builds."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> dict:
    """Read the configured workflow, including YAML's Boolean-key spelling of on."""
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def path_matches(pattern: str, filename: str) -> bool:
    """Match the *, ** and ? path globs used by these GitHub workflow filters."""
    expression = ""
    index = 0
    while index < len(pattern):
        if pattern[index : index + 3] == "**/":
            expression += "(?:.*/)?"
            index += 3
        elif pattern[index : index + 2] == "**":
            expression += ".*"
            index += 2
        elif pattern[index] == "*":
            expression += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            expression += "[^/]"
            index += 1
        else:
            expression += re.escape(pattern[index])
            index += 1
    return re.fullmatch(expression, filename) is not None


def triggers(name: str, filename: str) -> bool:
    """Apply ordered positive and negative filters to one changed PR path."""
    configured = workflow(name)
    events = configured.get("on", configured.get(True))
    included = False
    for pattern in events["pull_request"]["paths"]:
        if path_matches(pattern.removeprefix("!"), filename):
            included = not pattern.startswith("!")
    return included


@pytest.mark.parametrize(
    "filename",
    [
        "src/api/prompts/ask.md",
        "src/web/src/components/legals/EnAgreement.mdx",
        "src/i18n/en-US/common/core.json",
        "src/api/flaskr/service/shifu/route.py",
        "src/web/src/components/shifu-setting/ShifuSetting.tsx",
    ],
)
def test_application_changes_keep_production_coverage_without_arm64(
    filename: str,
) -> None:
    """Prompts, compiled Markdown and shared translations keep the runtime gate."""
    assert (ROOT / filename).is_file()
    assert triggers("runtime-harness.yml", filename)
    assert not triggers("docker-build-check.yml", filename)


@pytest.mark.parametrize(
    "filename",
    [
        "src/api/Dockerfile",
        "src/api/requirements.txt",
        "src/web/Dockerfile",
        "src/web/package.json",
        "src/web/package-lock.json",
        "src/web/scripts/check-production-dependencies.mjs",
        ".dockerignore",
        ".github/workflows/build-docker-image.yml",
        ".github/actions/docker-image-metadata/action.yml",
    ],
)
def test_packaging_inputs_receive_both_architecture_gates(filename: str) -> None:
    """Changes that can break packaging retain AMD64 runtime and ARM64 checks."""
    assert (ROOT / filename).is_file()
    assert triggers("runtime-harness.yml", filename)
    assert triggers("docker-build-check.yml", filename)


@pytest.mark.parametrize(
    "filename",
    [
        "src/api/tests/service/test_sample.py",
        "src/web/src/components/__tests__/sample.tsx",
        "src/web/src/components/sample.test.tsx",
        "docs/design-docs/sample.md",
    ],
)
def test_non_runtime_files_do_not_start_production_builds(filename: str) -> None:
    """Unit-test-only or external documentation changes do not create image jobs."""
    assert not triggers("runtime-harness.yml", filename)
    assert not triggers("docker-build-check.yml", filename)


def test_browser_harness_changes_still_run_runtime_checks() -> None:
    """Changes to the consuming browser tests must verify the production stack."""
    assert triggers("runtime-harness.yml", "src/web/e2e/fast-value.spec.ts")
    assert not triggers("docker-build-check.yml", "src/web/e2e/fast-value.spec.ts")


def test_runtime_build_smoke_and_browser_use_same_production_images() -> None:
    """The browser stack reuses the loaded images whose default startup was checked."""
    runtime = workflow("runtime-harness.yml")["jobs"]["runtime-harness"]
    steps = runtime["steps"]
    compose = yaml.safe_load(
        (ROOT / "docker/docker-compose.runtime-harness.yml").read_text()
    )["services"]
    builds = [
        step for step in steps if step.get("uses", "").startswith("docker/bake-action@")
    ]
    assert len(builds) == 1
    build = builds[0]["with"]
    assert build["load"] is True
    targets = build["targets"].split(",")
    assert set(targets) == {"ai-shifu-api-dev", "ai-shifu-cook-web-dev"}

    commands = [
        shlex.split(line)
        for step in steps
        for line in step.get("run", "").replace("\\\n", " ").splitlines()
        if "check_docker_image.py smoke" in line
    ]
    assert len(commands) == 2
    for service, target in [
        ("api", "ai-shifu-api-dev"),
        ("web", "ai-shifu-cook-web-dev"),
    ]:
        final_image = compose[target]
        assert final_image["build"] == {
            "context": "..",
            "dockerfile": f"src/{service}/Dockerfile",
        }
        assert not final_image.get("volumes"), (
            "Source mounts would replace the tested image contents"
        )
        invocation = next(
            command
            for command in commands
            if command[command.index("smoke") + 1] == service
        )
        smoke_arguments = invocation[invocation.index("smoke") + 1 :]
        assert smoke_arguments[:3] == [service, final_image["image"], "linux/amd64"]
        assert "--record" in smoke_arguments
        # Bake's CLI override uses singular "platform", unlike the JSON field.
        assert f"{target}.platform=linux/amd64" in build["set"]
        assert f"scope=ai-shifu-{service}-amd64" in build["set"]
    assert compose["ai-shifu-cook-web-dev"]["environment"]["I18N_ROOT"] == "/app/i18n"
    assert str(compose["ai-shifu-cook-web-dev"]["environment"]["PORT"]) == "5000"

    build_index = steps.index(builds[0])
    smoke_indices = [
        index
        for index, step in enumerate(steps)
        if "check_docker_image.py smoke" in step.get("run", "")
    ]
    starts = [
        (index, step["run"].replace("\\\n", " "))
        for index, step in enumerate(steps)
        if re.search(
            r"docker compose .*\bup\b", step.get("run", "").replace("\\\n", " ")
        )
    ]
    assert len(starts) == 1
    start_index, command = starts[0]
    assert build_index < min(smoke_indices) <= max(smoke_indices) < start_index
    assert "--no-build" in command
    assert "--pull never" in command
    assert not any("docker compose build" in step.get("run", "") for step in steps)

    infrastructure = set(compose) - set(targets)
    pulled = set()
    for step in steps[:start_index]:
        for line in step.get("run", "").replace("\\\n", " ").splitlines():
            if re.search(r"docker compose .*\bpull\b", line):
                arguments = shlex.split(line)
                pulled.update(arguments[arguments.index("pull") + 1 :])
    assert infrastructure <= pulled, (
        "A fresh runner needs infrastructure images before --pull never"
    )
    assert not pulled & set(targets), (
        "Pulling app images would replace the production smoke artifacts"
    )


def test_runtime_pr_validation_never_receives_publication_permissions() -> None:
    """Fork PR runtime validation only loads local images and never logs in."""
    runtime = workflow("runtime-harness.yml")
    assert runtime["permissions"] == {"contents": "read"}
    for job in runtime["jobs"].values():
        assert "permissions" not in job
        assert "secrets" not in job
        for step in job["steps"]:
            assert not step.get("uses", "").startswith("docker/login-action@")
            assert "secrets." not in str(step)
            if step.get("uses", "").startswith("docker/bake-action@"):
                assert not step["with"].get("push", False)


def test_runtime_and_native_builds_share_pinned_buildkit() -> None:
    """Layer reuse must not depend on two different BuildKit image versions."""
    options = []
    for filename in ["runtime-harness.yml", "build-docker-image.yml"]:
        setup = next(
            step
            for job in workflow(filename)["jobs"].values()
            for step in job.get("steps", [])
            if step.get("uses", "").startswith("docker/setup-buildx-action@")
        )
        options.append(setup["with"]["driver-opts"])
    assert options[0] == options[1]
    assert re.fullmatch(r"image=moby/buildkit:v\d+\.\d+\.\d+", options[0])


def test_pr_native_matrix_is_selected_and_excludes_amd64() -> None:
    """The PR packaging caller adds only the selected services' missing architecture."""
    jobs = workflow("docker-build-check.yml")["jobs"]
    selection = jobs["select-platforms"]
    native = jobs["native-build"]
    assert {"run", "matrix"} <= set(selection["outputs"])
    assert "select-platforms" in native["needs"]
    assert "needs.select-platforms.outputs.run" in native["if"]
    assert "needs.select-platforms.outputs.matrix" in str(native["strategy"]["matrix"])
    architectures = native["with"]["architectures"]
    branches = re.fullmatch(
        r"\$\{\{ github.event_name == 'pull_request' && '(.*?)' \|\| '(.*?)' }}",
        architectures,
    )
    assert branches is not None
    assert json.loads(branches[1]) == ["arm64"]
    assert json.loads(branches[2]) == ["amd64", "arm64"]


@pytest.mark.parametrize(
    ("filename", "job_name"),
    [
        ("build-latest.yml", "build-latest"),
        ("build-on-release.yml", "build-docker"),
        ("docker-build-check.yml", "candidate-build"),
    ],
)
def test_publication_callers_keep_default_both_native_architectures(
    filename: str,
    job_name: str,
) -> None:
    """Latest, release and candidate publication continue to validate both platforms."""
    reusable = workflow("build-docker-image.yml")
    events = reusable.get("on", reusable.get(True))
    assert json.loads(
        events["workflow_call"]["inputs"]["architectures"]["default"]
    ) == ["amd64", "arm64"]
    assert "inputs.architectures" in str(
        reusable["jobs"]["build"]["strategy"]["matrix"]
    )
    caller = workflow(filename)["jobs"][job_name]
    assert caller["uses"] == "./.github/workflows/build-docker-image.yml"
    assert "architectures" not in caller["with"]
