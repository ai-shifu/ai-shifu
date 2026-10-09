#!/usr/bin/env python3
"""Cover fail-closed publication and partial GitHub Actions reruns."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from merge_docker_manifests import load_digests, publish, verify_manifest


class ManifestPublicationTests(unittest.TestCase):
    """Protect platform completeness before moving any public image tag."""

    def setUp(self) -> None:
        """Create independent digest artifacts without using a registry."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.digests = {
            "linux/amd64": "sha256:" + "a" * 64,
            "linux/arm64": "sha256:" + "b" * 64,
        }
        self.metadata = {
            "tags": [
                "aishifu/web:latest",
                "aishifu/web:commit",
                "registry/ai-shifu/web:latest",
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
                ]
            }
        )

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
        with patch("merge_docker_manifests.docker") as run_docker:
            with pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"):
                publish(self.directory, self.metadata)
            run_docker.assert_not_called()

    def test_invalid_digest_never_publishes(self) -> None:
        """Malformed newer records cannot fall back silently to an older build."""
        self.write_digest("linux/arm64", "not-a-digest", 2)
        with patch("merge_docker_manifests.docker") as run_docker:
            with pytest.raises(ValueError, match=r"digest|Manifest|Duplicate|Both"):
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
        assert sum(args[:2] == ("inspect", "--raw") for args in calls) == 3

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

    def test_ghcr_and_both_mirrors_use_the_same_native_digests(self) -> None:
        """Every destination must preflight both architectures before publication."""
        self.metadata["tags"].append("ghcr.io/ai-shifu/web:latest")
        with patch(
            "merge_docker_manifests.docker", return_value=self.manifest()
        ) as run_docker:
            publish(self.directory, self.metadata)
        calls = [call.args for call in run_docker.call_args_list]
        assert [args[:2] for args in calls[:3]] == [("create", "--dry-run")] * 3
        assert calls[3][:2] != ("create", "--dry-run")
        for registry in (
            "aishifu/web",
            "registry/ai-shifu/web",
            "ghcr.io/ai-shifu/web",
        ):
            writes = [
                args
                for args in calls
                if args[:2] == ("create", "--tag") and f"{registry}:latest" in args
            ]
            assert len(writes) == 1
            for digest in self.digests.values():
                assert f"{registry}@{digest}" in writes[0]
        assert ("inspect", "--raw", "ghcr.io/ai-shifu/web:latest") in calls

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
            publish(self.directory, {"tags": ["aishifu/web:latest"]})

    def test_invalid_tags_prevent_registry_calls(self) -> None:
        """Malformed destination metadata must fail before touching registries."""
        for tags in [[], ["web"], ["aishifu/web:bad tag"], ["aishifu/web@sha256:abc"]]:
            with patch("merge_docker_manifests.docker") as run_docker:
                with pytest.raises(ValueError, match="tag"):
                    publish(self.directory, {"tags": tags})
                run_docker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
