#!/usr/bin/env python3
"""Protect global readiness, immutable deployment inputs, and publication order."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from promote_docker_images import (
    ATTEMPT_ANNOTATION,
    RUN_ANNOTATION,
    StalePublicationError,
    compose_override,
    ensure_current_main,
    ensure_not_newer,
    load_publication,
    promote,
)


class CompletePublicationTests(unittest.TestCase):
    """Exercise service artifact carryover and registry promotion without credentials."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.sha = "a" * 40
        self.run_id = "200"
        self.platforms = {
            "linux/amd64": "sha256:" + "b" * 64,
            "linux/arm64": "sha256:" + "c" * 64,
        }
        self.index = "sha256:" + "d" * 64
        self.write_service("api", 1)
        self.write_service("web", 1)
        self.descriptor = load_publication(self.directory, self.sha, self.run_id, 1)
        self.status = self.directory / "publication-status.json"

    def write_service(
        self, service: str, attempt: int, registry: str = "docker.io"
    ) -> Path:
        artifact = self.directory / f"docker-publication-{service}-{attempt}"
        artifact.mkdir(exist_ok=True)
        repository = (
            f"aishifu/{service}"
            if registry == "docker.io"
            else f"{registry}/ai-shifu/{service}"
        )
        record = {
            "schema_version": 1,
            "service": service,
            "source": {"sha": self.sha, "run_id": self.run_id, "run_attempt": attempt},
            "images": [
                {
                    "repository": repository,
                    "digest": self.index,
                    "platforms": self.platforms,
                }
            ],
        }
        path = artifact / "service.json"
        path.write_text(json.dumps(record))
        return path

    def manifest(self, run_id: str | None = None, attempt: int = 1) -> str:
        result = {
            "digest": self.index,
            "manifests": [
                {
                    "digest": digest,
                    "platform": {"os": "linux", "architecture": platform.split("/")[1]},
                }
                for platform, digest in self.platforms.items()
            ],
        }
        if run_id is not None:
            result["annotations"] = {
                RUN_ANNOTATION: run_id,
                ATTEMPT_ANNOTATION: str(attempt),
            }
        return json.dumps(result)

    def test_all_services_are_required_before_deployment_or_promotion(self) -> None:
        (self.directory / "docker-publication-web-1/service.json").unlink()
        with pytest.raises(ValueError, match="API and web"):
            load_publication(self.directory, self.sha, self.run_id, 1)

    def test_successful_services_carry_across_failed_job_attempts(self) -> None:
        self.write_service("web", 2)
        descriptor = load_publication(self.directory, self.sha, self.run_id, 2)
        assert descriptor["services"]["api"]["build_attempt"] == 1
        assert descriptor["services"]["web"]["build_attempt"] == 2
        assert descriptor["source"]["run_attempt"] == 2

    def test_wrong_run_sha_and_future_attempt_cannot_be_deployed(self) -> None:
        for sha, run_id, attempt in (
            ("e" * 40, self.run_id, 1),
            (self.sha, "199", 1),
            (self.sha, self.run_id, 0),
        ):
            with pytest.raises(ValueError, match=r"provenance|source"):
                load_publication(self.directory, sha, run_id, attempt)
        self.write_service("web", 2)
        with pytest.raises(ValueError, match="provenance"):
            load_publication(self.directory, self.sha, self.run_id, 1)

    def test_registry_sets_must_match_for_api_and_web(self) -> None:
        self.write_service("web", 2, "registry.example.com")
        with pytest.raises(ValueError, match="destinations differ"):
            load_publication(self.directory, self.sha, self.run_id, 2)

    def test_compose_override_pins_web_and_all_api_processes(self) -> None:
        override = compose_override(self.descriptor, "docker.io")
        assert set(override["services"]) == {
            "ai-shifu-api",
            "ai-shifu-celery-worker",
            "ai-shifu-celery-beat",
            "ai-shifu-cook-web",
        }
        for name, image in override["services"].items():
            service = "web" if name == "ai-shifu-cook-web" else "api"
            assert image["image"] == f"aishifu/{service}@{self.index}"
        with pytest.raises(ValueError, match="Exactly one"):
            compose_override(self.descriptor, "unconfigured.example.com")

    def test_non_main_dispatch_cannot_promote_latest(self) -> None:
        with (
            patch.dict("os.environ", {"GITHUB_REF": "refs/heads/feature"}),
            patch("promote_docker_images.subprocess.run") as run_command,
            pytest.raises(ValueError, match="Only main"),
        ):
            ensure_current_main(self.sha)
        run_command.assert_not_called()

    def test_old_commit_cannot_promote_after_main_advances(self) -> None:
        response = subprocess.CompletedProcess(
            ["git"], 0, stdout="e" * 40 + "\trefs/heads/main\n"
        )
        with (
            patch.dict("os.environ", {"GITHUB_REF": "refs/heads/main"}),
            patch("promote_docker_images.subprocess.run", return_value=response),
            pytest.raises(StalePublicationError, match="advanced"),
        ):
            ensure_current_main(self.sha)

    def test_newer_run_and_attempt_protect_same_sha_rebuilds(self) -> None:
        image = self.descriptor["services"]["api"]["images"][0]
        for current in (self.manifest("201"), self.manifest(self.run_id, 2)):
            with (
                patch("promote_docker_images.docker", return_value=current),
                pytest.raises(StalePublicationError, match="newer workflow"),
            ):
                ensure_not_newer(image, self.descriptor["source"], 1)

    def test_missing_latest_allows_initial_publication_but_auth_failure_does_not(
        self,
    ) -> None:
        image = self.descriptor["services"]["api"]["images"][0]
        for detail, missing in (
            ("manifest unknown", True),
            ("unauthorized: not found", False),
        ):
            failure = subprocess.CalledProcessError(1, "docker", stderr=detail)
            with patch("promote_docker_images.docker", side_effect=failure):
                if missing:
                    ensure_not_newer(image, self.descriptor["source"], 1)
                else:
                    with pytest.raises(subprocess.CalledProcessError):
                        ensure_not_newer(image, self.descriptor["source"], 1)

    def test_stale_preflight_never_moves_a_tag(self) -> None:
        with (
            patch(
                "promote_docker_images.ensure_current_main",
                side_effect=StalePublicationError("advanced"),
            ),
            patch("promote_docker_images.docker") as run_docker,
            pytest.raises(StalePublicationError),
        ):
            promote(self.descriptor, self.status)
        run_docker.assert_not_called()
        assert json.loads(self.status.read_text())["state"] == "stale"

    def test_every_service_preflights_before_latest_changes(self) -> None:
        with (
            patch("promote_docker_images.ensure_current_main"),
            patch("promote_docker_images.ensure_not_newer"),
            patch(
                "promote_docker_images.inspect_digest", return_value=self.index
            ) as inspect,
            patch("promote_docker_images.docker") as run_docker,
        ):
            promote(self.descriptor, self.status)
        assert [call.args[0] for call in inspect.call_args_list[:2]] == [
            f"aishifu/api@{self.index}",
            f"aishifu/web@{self.index}",
        ]
        assert run_docker.call_count == 2
        assert json.loads(self.status.read_text())["state"] == "verified"

    def test_partial_registry_failure_is_recoverable_with_the_saved_descriptor(
        self,
    ) -> None:
        failure = subprocess.CalledProcessError(1, "docker", stderr="denied")
        with (
            patch("promote_docker_images.ensure_current_main"),
            patch("promote_docker_images.ensure_not_newer"),
            patch("promote_docker_images.inspect_digest", return_value=self.index),
            patch("promote_docker_images.docker", side_effect=["", failure]),
            pytest.raises(subprocess.CalledProcessError),
        ):
            promote(self.descriptor, self.status)
        status = json.loads(self.status.read_text())
        assert status["state"] == "failed"
        assert [target["state"] for target in status["targets"]] == [
            "verified",
            "unverified",
        ]
        original_identity = status["descriptor_sha256"]
        with (
            patch("promote_docker_images.ensure_current_main"),
            patch("promote_docker_images.ensure_not_newer"),
            patch("promote_docker_images.inspect_digest", return_value=self.index),
            patch("promote_docker_images.docker"),
        ):
            promote(self.descriptor, self.status)
        recovered = json.loads(self.status.read_text())
        assert recovered["descriptor_sha256"] == original_identity
        assert recovered["state"] == "verified"

    def test_main_advancing_between_mutations_leaves_partial_status(self) -> None:
        with (
            patch(
                "promote_docker_images.ensure_current_main",
                side_effect=[None, None, StalePublicationError("advanced")],
            ),
            patch("promote_docker_images.ensure_not_newer"),
            patch("promote_docker_images.inspect_digest", return_value=self.index),
            patch("promote_docker_images.docker") as run_docker,
            pytest.raises(StalePublicationError),
        ):
            promote(self.descriptor, self.status)
        assert run_docker.call_count == 1
        status = json.loads(self.status.read_text())
        assert status["state"] == "stale"
        assert [target["state"] for target in status["targets"]] == [
            "verified",
            "pending",
        ]


if __name__ == "__main__":
    unittest.main()
