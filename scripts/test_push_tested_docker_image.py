#!/usr/bin/env python3
"""Cover cached native export retries and the tested-content handoff boundary."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from push_tested_docker_image import (
    build_command,
    cached_graph,
    push_tested,
    retryable_export,
)

CACHED_LOG = """#10 [deps 2/3] RUN npm ci
#10 CACHED
#22 [builder 4/4] RUN npm run build
#22 CACHED
#30 exporting to image
#30 exporting layers done
"""


def transport_log(detail: str = "TLS handshake timeout") -> str:
    """Model the exporter-owned OAuth failure from the historical build log."""
    return (
        CACHED_LOG
        + f"#30 ERROR: failed to authorize: failed to fetch oauth token: {detail}\nERROR: failed to build: failed to solve: failed to push registry/web: failed to authorize: {detail}\n"
    )


class CachedExportTests(unittest.TestCase):
    """Validate exporter decisions without building or accessing a registry."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.metadata = self.directory / "push.json"
        self.record = {
            "service": "web",
            "platform": "linux/arm64",
            "config_digest": "sha256:" + "a" * 64,
        }
        self.digest = "sha256:" + "b" * 64
        environment = patch.dict(
            "os.environ",
            {"IMAGE_LABELS": "", "IMAGE_ANNOTATIONS": "", "IMAGE_BUILD_ARGS": ""},
        )
        environment.start()
        self.addCleanup(environment.stop)

    def successful_export(
        self, command: list[str], *, capture_output: bool, text: bool, check: bool
    ) -> subprocess.CompletedProcess:
        assert command[:3] == ["docker", "buildx", "build"]
        assert capture_output
        assert text
        assert not check
        self.metadata.write_text(
            json.dumps(
                {
                    "containerimage.digest": self.digest,
                    "containerimage.config.digest": self.record["config_digest"],
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=CACHED_LOG)

    def invoke(self) -> str:
        return push_tested(
            "tested-builder",
            "src/web/Dockerfile",
            "aishifu/web,registry.example.com/ai-shifu/web",
            self.record,
            self.metadata,
        )

    def test_export_preserves_exact_inputs_and_oci_compatibility_flags(self) -> None:
        environment = {
            "IMAGE_LABELS": "org.example.title=AI Shifu\norg.example.value=literal `value`",
            "IMAGE_ANNOTATIONS": "manifest:org.example.source=main",
            "IMAGE_BUILD_ARGS": "TAG_VERSION=v1.2.3",
        }
        with patch.dict("os.environ", environment):
            command = build_command(
                "tested-builder",
                "src/web/Dockerfile",
                "aishifu/web,registry.example.com/ai-shifu/web",
                self.record,
                self.metadata,
            )
        assert command[command.index("--builder") + 1] == "tested-builder"
        assert command[command.index("--platform") + 1] == "linux/arm64"
        assert (
            command[command.index("--output") + 1]
            == 'type=image,"name=aishifu/web,registry.example.com/ai-shifu/web",push-by-digest=true,name-canonical=true,push=true,oci-mediatypes=true'
        )
        assert "--provenance=false" in command
        assert "--sbom=false" in command
        assert "org.example.title=AI Shifu" in command
        assert "org.example.value=literal `value`" in command
        assert "manifest:org.example.source=main" in command
        assert "TAG_VERSION=v1.2.3" in command
        assert "--cache-from" not in command
        assert "--cache-to" not in command
        assert "--no-cache" not in command
        assert command[-1] == "."

    def test_missing_smoke_or_builder_cannot_start_an_export(self) -> None:
        with (
            patch("push_tested_docker_image.subprocess.run") as run_command,
            pytest.raises(ValueError, match="production-smoke"),
        ):
            push_tested(
                "tested-builder", "src/web/Dockerfile", "aishifu/web", {}, self.metadata
            )
        run_command.assert_not_called()
        with pytest.raises(ValueError, match="production-smoke"):
            build_command(
                "", "src/web/Dockerfile", "aishifu/web", self.record, self.metadata
            )

    def test_cached_export_returns_only_the_smoke_matching_digest(self) -> None:
        with patch(
            "push_tested_docker_image.subprocess.run",
            side_effect=self.successful_export,
        ) as run_command:
            assert self.invoke() == self.digest
        assert run_command.call_count == 1

    def test_transport_retry_repeats_only_an_identical_cached_export(self) -> None:
        failure = subprocess.CompletedProcess(
            ["docker"], 1, stdout="", stderr=transport_log()
        )
        responses = [failure]

        def export_after_failure(
            command: list[str], *, capture_output: bool, text: bool, check: bool
        ) -> subprocess.CompletedProcess:
            if responses:
                return responses.pop()
            return self.successful_export(
                command, capture_output=capture_output, text=text, check=check
            )

        with (
            patch(
                "push_tested_docker_image.subprocess.run",
                side_effect=export_after_failure,
            ) as run_command,
            patch("push_tested_docker_image.time.sleep") as sleep,
        ):
            assert self.invoke() == self.digest
        assert run_command.call_count == 2
        assert run_command.call_args_list[0] == run_command.call_args_list[1]
        sleep.assert_called_once_with(1)

    def test_exporter_oauth_tls_failure_is_retryable_but_auth_is_not(self) -> None:
        assert retryable_export(transport_log())
        for detail in (
            "unauthorized: TLS handshake timeout",
            "unsupported media type",
            "certificate signed by unknown authority",
            "manifest invalid",
            "illegal instruction: exit code 132",
        ):
            assert not retryable_export(transport_log(detail))

    def test_non_exporter_and_uncached_build_failures_never_retry(self) -> None:
        dependency_error = (
            CACHED_LOG
            + "#22 ERROR: process npm ci: connection reset by peer\nERROR: failed to build: failed to solve: process npm ci: connection reset by peer\n"
        )
        assert not retryable_export(dependency_error)
        assert not retryable_export(
            transport_log().replace("#22 CACHED", "#22 DONE 4.0s")
        )
        assert not cached_graph("#30 exporting to image\n")
        assert not retryable_export(
            "ERROR: failed to push registry/web: TLS handshake timeout\n"
        )

    def test_bounded_failures_do_not_retry_compile_auth_or_missing_cache(self) -> None:
        for log in (
            transport_log("denied: TLS handshake timeout"),
            transport_log("unsupported media type"),
            transport_log().replace(
                "#22 CACHED", "#22 ERROR: npm failed with exit code 132"
            ),
        ):
            failure = subprocess.CompletedProcess(["docker"], 1, stdout="", stderr=log)
            with (
                patch(
                    "push_tested_docker_image.subprocess.run", return_value=failure
                ) as run_command,
                patch("push_tested_docker_image.time.sleep") as sleep,
                pytest.raises(subprocess.CalledProcessError),
            ):
                self.invoke()
            assert run_command.call_count == 1
            sleep.assert_not_called()

    def test_transport_retry_exhaustion_is_visible_after_three_attempts(self) -> None:
        failure = subprocess.CompletedProcess(
            ["docker"], 1, stdout="", stderr=transport_log("connection reset by peer")
        )
        with (
            patch(
                "push_tested_docker_image.subprocess.run", return_value=failure
            ) as run_command,
            patch("push_tested_docker_image.time.sleep") as sleep,
            pytest.raises(subprocess.CalledProcessError),
        ):
            self.invoke()
        assert run_command.call_count == 3
        assert [call.args for call in sleep.call_args_list] == [(1,), (2,)]
        assert len({tuple(call.args[0]) for call in run_command.call_args_list}) == 1

    def test_successful_command_without_cache_proof_cannot_export_a_digest(
        self,
    ) -> None:
        success = subprocess.CompletedProcess(
            ["docker"],
            0,
            stdout="",
            stderr=CACHED_LOG.replace("#22 CACHED", "#22 DONE 4.0s"),
        )
        with (
            patch("push_tested_docker_image.subprocess.run", return_value=success),
            pytest.raises(ValueError, match="all RUN steps"),
        ):
            self.invoke()

    def test_wrong_config_and_invalid_digest_never_produce_a_handoff(self) -> None:
        success = subprocess.CompletedProcess(
            ["docker"], 0, stdout="", stderr=CACHED_LOG
        )
        for metadata in (
            {
                "containerimage.digest": self.digest,
                "containerimage.config.digest": "sha256:" + "c" * 64,
            },
            {
                "containerimage.digest": "bad",
                "containerimage.config.digest": self.record["config_digest"],
            },
        ):

            def export_with_bad_metadata(
                command: list[str], metadata_value: dict = metadata, **options: object
            ) -> subprocess.CompletedProcess:
                assert command
                assert options
                self.metadata.write_text(json.dumps(metadata_value))
                return success

            with (
                patch(
                    "push_tested_docker_image.subprocess.run",
                    side_effect=export_with_bad_metadata,
                ),
                pytest.raises(ValueError, match="differs"),
            ):
                self.invoke()


if __name__ == "__main__":
    unittest.main()
