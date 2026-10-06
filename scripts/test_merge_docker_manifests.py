#!/usr/bin/env python3
"""Cover fail-closed publication and partial GitHub Actions reruns."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from merge_docker_manifests import (
    docker,
    inspect_digest,
    load_digests,
    publish,
    verify_manifest,
)


class ManifestPublicationTests(unittest.TestCase):
    """Protect platform completeness before moving any public image tag."""

    def setUp(self) -> None:
        """Create independent digest artifacts without using a registry."""
        environment = patch.dict(os.environ, {"GITHUB_RUN_ID": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.digests = {
            "linux/amd64": "sha256:" + "a" * 64,
            "linux/arm64": "sha256:" + "b" * 64,
        }
        self.metadata = {
            "tags": [
                "aishifu/web:candidate",
                "aishifu/web:commit",
                "registry/ai-shifu/web:candidate",
            ]
        }
        for platform, digest in self.digests.items():
            self.write_digest(platform, digest, 1)

    def write_digest(self, platform: str, digest: str, attempt: int) -> None:
        """Model an uploaded digest from one successful native build."""
        arch = platform.split("/")[1]
        artifact = self.directory / f"docker-digest-web-{arch}-{attempt}"
        artifact.mkdir(exist_ok=True)
        (artifact / f"{arch}.json").write_text(
            json.dumps({"platform": platform, "digest": digest})
        )

    def manifest(self, digests: dict[str, str] | None = None) -> str:
        """Produce a registry manifest for the requested platform/digest set."""
        return json.dumps(
            {
                "digest": "sha256:" + "e" * 64,
                "manifests": [
                    {
                        "digest": digest,
                        "platform": {
                            "os": platform.split("/")[0],
                            "architecture": platform.split("/")[1],
                        },
                    }
                    for platform, digest in (
                        self.digests if digests is None else digests
                    ).items()
                ],
            }
        )

    def test_index_annotations_are_required_for_ordered_publication(self) -> None:
        """Ordering protection requires metadata preserved on the registry index."""
        expected = {
            "io.ai-shifu.publication.run-id": "200",
            "io.ai-shifu.publication.run-attempt": "1",
        }
        with (
            patch("merge_docker_manifests.docker", return_value=self.manifest()),
            pytest.raises(ValueError, match="annotations differ"),
        ):
            inspect_digest("aishifu/web:candidate", self.digests, expected)
        manifest = json.loads(self.manifest())
        manifest["annotations"] = expected
        with patch("merge_docker_manifests.docker", return_value=json.dumps(manifest)):
            assert (
                inspect_digest("aishifu/web:candidate", self.digests, expected)
                == "sha256:" + "e" * 64
            )

    def test_preflight_failure_records_no_attempted_tag_writes(self) -> None:
        """All destination readiness failures leave only pending tags in the report."""
        status = self.directory / "status.json"
        failure = subprocess.CalledProcessError(1, "docker", stderr="denied")
        with (
            patch(
                "merge_docker_manifests.docker", side_effect=[self.manifest(), failure]
            ),
            pytest.raises(subprocess.CalledProcessError),
        ):
            publish(self.directory, self.metadata, status)
        report = json.loads(status.read_text())
        assert report["state"] == "failed"
        assert all(target["state"] == "pending" for target in report["targets"])

    def test_direct_latest_publication_is_rejected(self) -> None:
        """A service cannot bypass the coordinated main channel promotion."""
        with (
            patch("merge_docker_manifests.docker") as run_docker,
            pytest.raises(ValueError, match="coordinated main"),
        ):
            publish(self.directory, {"tags": ["aishifu/web:latest"]})
        run_docker.assert_not_called()

    def test_transport_failures_retry_only_the_same_registry_operation(self) -> None:
        """An OAuth TLS handshake timeout retries the manifest command twice."""
        failure = subprocess.CalledProcessError(
            1, "docker", stderr="failed to fetch oauth token: TLS handshake timeout"
        )
        success = subprocess.CompletedProcess(["docker"], 0, stdout="manifest")
        with (
            patch(
                "merge_docker_manifests.subprocess.run", side_effect=[failure, success]
            ) as run_command,
            patch("merge_docker_manifests.time.sleep") as sleep,
        ):
            assert (
                docker(
                    "create", "--tag", "registry/web:candidate", "registry/web@digest"
                )
                == "manifest"
            )
        assert run_command.call_count == 2
        assert run_command.call_args_list[0] == run_command.call_args_list[1]
        sleep.assert_called_once_with(1)

    def test_permanent_registry_errors_never_retry(self) -> None:
        """Credentials, media types, and TLS trust are not transient transport errors."""
        for detail in (
            "unauthorized: TLS handshake timeout",
            "unsupported media type",
            "certificate signed by unknown authority",
            "manifest unknown",
        ):
            failure = subprocess.CalledProcessError(1, "docker", stderr=detail)
            with (
                patch(
                    "merge_docker_manifests.subprocess.run", side_effect=failure
                ) as run_command,
                patch("merge_docker_manifests.time.sleep") as sleep,
                pytest.raises(subprocess.CalledProcessError),
            ):
                docker("inspect", "--raw", "registry/web:candidate")
            assert run_command.call_count == 1
            sleep.assert_not_called()

    def test_transport_retries_are_bounded(self) -> None:
        """A persistent connection reset fails after three identical operations."""
        failure = subprocess.CalledProcessError(
            1, "docker", stderr="connection reset by peer"
        )
        with (
            patch(
                "merge_docker_manifests.subprocess.run", side_effect=failure
            ) as run_command,
            patch("merge_docker_manifests.time.sleep") as sleep,
            pytest.raises(subprocess.CalledProcessError),
        ):
            docker("inspect", "--raw", "registry/web:candidate")
        assert run_command.call_count == 3
        assert sleep.call_count == 2

    def test_service_failure_records_verified_and_unverified_destinations(self) -> None:
        """Partial registry writes remain visible and never claim an atomic rollback."""
        status = self.directory / "status.json"
        failure = subprocess.CalledProcessError(1, "docker", stderr="denied")
        with (
            patch(
                "merge_docker_manifests.docker",
                side_effect=[
                    self.manifest(),
                    self.manifest(),
                    "",
                    self.manifest(),
                    self.manifest(),
                    failure,
                ],
            ),
            pytest.raises(subprocess.CalledProcessError),
        ):
            publish(self.directory, self.metadata, status)
        records = json.loads(status.read_text())
        assert [target["state"] for target in records["targets"]] == [
            "verified",
            "verified",
            "unverified",
        ]
        assert records["error_type"] == "CalledProcessError"

    def test_failed_job_rerun_preserves_other_platform(self) -> None:
        """A failed ARM retry must use the new ARM digest and successful AMD digest."""
        replacement = "sha256:" + "c" * 64
        self.write_digest("linux/arm64", replacement, 2)
        assert load_digests(self.directory) == {
            **self.digests,
            "linux/arm64": replacement,
        }

    def test_missing_platform_never_publishes(self) -> None:
        """Incomplete artifact sets fail before invoking Docker."""
        for path in self.directory.glob("*arm64*/*.json"):
            path.unlink()
        with (
            patch("merge_docker_manifests.docker") as run_docker,
            pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"),
        ):
            publish(self.directory, self.metadata)
        run_docker.assert_not_called()

    def test_invalid_digest_never_publishes(self) -> None:
        """Malformed newer records cannot fall back silently to an older build."""
        self.write_digest("linux/arm64", "not-a-digest", 2)
        with (
            patch("merge_docker_manifests.docker") as run_docker,
            pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"),
        ):
            publish(self.directory, self.metadata)
        run_docker.assert_not_called()

    def test_preflights_every_registry_before_publishing(self) -> None:
        """Both platforms and all destinations must resolve before tags change."""
        with patch(
            "merge_docker_manifests.docker", return_value=self.manifest()
        ) as run_docker:
            publish(self.directory, self.metadata)
        calls = [call.args for call in run_docker.call_args_list]
        assert [args[:2] for args in calls[:2]] == [("create", "--dry-run")] * 2
        assert "aishifu/web@" + self.digests["linux/arm64"] in calls[0]
        assert "registry/ai-shifu/web@" + self.digests["linux/arm64"] in calls[1]
        assert sum(args[:2] == ("inspect", "--format") for args in calls) == 3

    def test_bad_second_registry_does_not_move_first_registry_tags(self) -> None:
        """A registry missing an architecture fails during preflight."""
        with (
            patch(
                "merge_docker_manifests.docker",
                side_effect=[
                    self.manifest(),
                    self.manifest({"linux/amd64": self.digests["linux/amd64"]}),
                ],
            ) as run_docker,
            pytest.raises(ValueError, match="Manifest platforms"),
        ):
            publish(self.directory, self.metadata)
        assert all(
            call.args[:2] == ("create", "--dry-run")
            for call in run_docker.call_args_list
        )

    def test_rejects_wrong_and_duplicate_manifest_platforms(self) -> None:
        """Successful CLI exit alone cannot prove a correct multi-platform image."""
        wrong = self.manifest({**self.digests, "linux/arm64": "sha256:" + "d" * 64})
        with pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"):
            verify_manifest(wrong, self.digests)
        duplicate = json.loads(self.manifest())
        duplicate["manifests"].append(duplicate["manifests"][0])
        with pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"):
            verify_manifest(json.dumps(duplicate), self.digests)

    def test_registry_failure_propagates_without_retry(self) -> None:
        """Registry failures must stay visible rather than triggering build retries."""
        with (
            patch(
                "merge_docker_manifests.docker",
                side_effect=subprocess.CalledProcessError(1, "docker"),
            ) as run_docker,
            pytest.raises(subprocess.CalledProcessError),
        ):
            publish(self.directory, self.metadata)
        assert run_docker.call_count == 1

    def test_post_publication_platform_mismatch_is_failure(self) -> None:
        """Successful CLI output cannot hide a final index missing a platform."""
        with (
            patch(
                "merge_docker_manifests.docker",
                side_effect=[self.manifest(), "", self.manifest({})],
            ),
            pytest.raises(ValueError, match="Manifest platforms"),
        ):
            publish(self.directory, {"tags": ["aishifu/web:candidate"]})

    def test_invalid_tags_prevent_registry_calls(self) -> None:
        """Malformed destination metadata must fail before touching registries."""
        for tags in [[], ["web"], ["aishifu/web:bad tag"], ["aishifu/web@sha256:abc"]]:
            with (
                patch("merge_docker_manifests.docker") as run_docker,
                pytest.raises(ValueError, match="tag"),
            ):
                publish(self.directory, {"tags": tags})
            run_docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
