#!/usr/bin/env python3
"""Protect production smoke failures and the exact tested-image publication gate."""

from __future__ import annotations

import json
import subprocess
import unittest
from fnmatch import fnmatchcase
from pathlib import Path
from unittest.mock import patch

import pytest
from check_docker_image import (
    docker,
    smoke,
    validate_health,
    validate_i18n,
    verify_published,
)

CONFIG = "sha256:" + "a" * 64
MANIFEST = "sha256:" + "b" * 64


class ProductionImageTests(unittest.TestCase):
    """Require final-image startup and immutable content verification."""

    def image(self, platform: str = "amd64") -> str:
        """Describe a final image as Docker's local image inspect does."""
        return json.dumps(
            [
                {
                    "Os": "linux",
                    "Architecture": platform,
                    "Id": CONFIG,
                    "Config": {"User": "node"},
                }
            ]
        )

    def docker(self, *args: str) -> str:
        """Model a daemon that starts a container on an isolated loopback port."""
        if args[:2] == ("image", "inspect"):
            return self.image()
        if args[:2] == ("run", "-d"):
            return "smoke-container"
        if args[0] == "port":
            return "127.0.0.1:31000"
        return ""

    def test_http_200_business_error_is_unhealthy(self) -> None:
        """The API's HTTP-200 error envelope cannot make packaging smoke pass."""
        for value in ({"code": 1, "data": "ok"}, {"code": 0, "data": "error"}, {}):
            with pytest.raises(ValueError, match="health response"):
                validate_health(json.dumps(value).encode())
        validate_health(b'{"code":0,"data":"ok"}')

    def test_startup_diagnostics_include_application_stderr(self) -> None:
        """Gunicorn errors on stderr must survive a failed production smoke check."""
        result = subprocess.CompletedProcess(
            ["docker", "logs", "smoke-container"],
            0,
            stdout="starting\n",
            stderr="worker failed to boot\n",
        )
        with patch("check_docker_image.subprocess.run", return_value=result):
            assert "worker failed to boot" in docker("logs", "smoke-container")

    def test_production_markdown_triggers_packaging_checks(self) -> None:
        """Compiled legal pages and API prompt changes must receive native checks."""
        repository = Path(__file__).resolve().parents[1]
        workflow = (repository / ".github/workflows/docker-build-check.yml").read_text()
        paths = workflow.split("    paths:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        patterns = [
            line.strip()[2:].strip("'\"")
            for line in paths.splitlines()
            if line.strip().startswith("- ")
        ]
        for filename in (
            "src/web/src/components/legals/EnAgreement.mdx",
            "src/api/prompts/ask.md",
            "src/web/package-lock.json",
            "src/i18n/en-US/common/core.json",
        ):
            assert (repository / filename).is_file()
            included = False
            for pattern in patterns:
                excluded = pattern.startswith("!")
                if fnmatchcase(filename, pattern.removeprefix("!")):
                    included = not excluded
            assert included, f"Production input misses packaging validation: {filename}"

    def test_i18n_requires_real_shared_resource(self) -> None:
        """An empty or wrong-locale response cannot hide a missing runtime resource."""
        valid = {
            "language": "en-US",
            "missingNamespaces": [],
            "translations": {"common.core": {"ok": "OK"}},
        }
        validate_i18n(json.dumps(valid).encode())
        for key, value in (
            ("translations", {}),
            ("language", "zh-CN"),
            ("missingNamespaces", ["common.core"]),
        ):
            with pytest.raises(ValueError, match="i18n resources"):
                validate_i18n(json.dumps({**valid, key: value}).encode())

    def test_api_default_startup_and_cleanup(self) -> None:
        """Smoke uses the image command with fake local-only configuration and cleans up."""
        with (
            patch("check_docker_image.docker", side_effect=self.docker) as daemon,
            patch(
                "check_docker_image.wait_for_http",
                return_value=b'{"code":0,"data":"ok"}',
            ),
        ):
            assert smoke("api", "local:api", "linux/amd64") == {
                "service": "api",
                "platform": "linux/amd64",
                "config_digest": CONFIG,
            }
        calls = [entry.args for entry in daemon.call_args_list]
        startup = next(args for args in calls if args[:2] == ("run", "-d"))
        assert startup[-1] == "local:api"
        assert "--entrypoint" not in startup
        assert "OPENAI_BASE_URL=http://127.0.0.1:9/v1" in startup
        assert calls[-1] == ("rm", "--force", "smoke-container")

    def test_bad_runtime_response_still_removes_container(self) -> None:
        """A bad startup result emits logs and cannot leak its detached container."""
        with (
            patch("check_docker_image.docker", side_effect=self.docker) as daemon,
            patch("check_docker_image.wait_for_http", return_value=b'{"code":1}'),
            pytest.raises(ValueError, match="health response"),
        ):
            smoke("api", "local:api", "linux/amd64")
        assert daemon.call_args_list[-2].args == ("logs", "smoke-container")
        assert daemon.call_args_list[-1].args == ("rm", "--force", "smoke-container")

    def test_wrong_architecture_never_starts(self) -> None:
        """A cached image for the other architecture cannot satisfy a native check."""
        with (
            patch("check_docker_image.docker", return_value=self.image()) as daemon,
            pytest.raises(ValueError, match="platform/config"),
        ):
            smoke("web", "local:web", "linux/arm64")
        assert daemon.call_count == 1

    def test_web_checks_runtime_config_i18n_and_static_assets(self) -> None:
        """The final runner must serve compiled assets and translations as non-root."""
        i18n = b'{"language":"en-US","missingNamespaces":[],"translations":{"common.core":{"ok":"OK"}}}'
        with (
            patch("check_docker_image.docker", side_effect=self.docker),
            patch(
                "check_docker_image.wait_for_http",
                return_value=b'{"apiBaseUrl":"http://localhost:5800"}',
            ),
            patch(
                "check_docker_image.read_http",
                side_effect=[
                    i18n,
                    b"<svg/>",
                    b'<html><script src="/_next/static/chunk.js"></script></html>',
                    b"javascript",
                ],
            ),
        ):
            smoke("web", "local:web", "linux/amd64")

    def test_every_registry_must_match_tested_config(self) -> None:
        """Different published filesystem/config fails even when all pushes succeeded."""
        record = {"platform": "linux/amd64", "config_digest": CONFIG}
        with (
            patch(
                "check_docker_image.published_config", side_effect=[CONFIG, MANIFEST]
            ) as inspect,
            pytest.raises(ValueError, match="differs from"),
        ):
            verify_published(record, "dockerhub/api,registry/api", MANIFEST)
        assert inspect.call_count == 2

    def test_published_index_resolves_exact_target_platform(self) -> None:
        """OCI index exporters must resolve the tested platform before config comparison."""
        index = {
            "manifests": [
                {
                    "digest": MANIFEST,
                    "platform": {"os": "linux", "architecture": "amd64"},
                }
            ]
        }
        with patch(
            "check_docker_image.docker",
            side_effect=[json.dumps(index), json.dumps({"config": {"digest": CONFIG}})],
        ) as daemon:
            verify_published(
                {"platform": "linux/amd64", "config_digest": CONFIG},
                "registry/api",
                MANIFEST,
            )
        assert daemon.call_count == 2

    def test_invalid_fingerprint_does_not_query_registry(self) -> None:
        """A missing smoke record cannot be replaced by merely checking a pushed tag."""
        with (
            patch("check_docker_image.docker") as daemon,
            pytest.raises(ValueError, match="Invalid smoke"),
        ):
            verify_published({"platform": "linux/arm64"}, "registry/api", MANIFEST)
        daemon.assert_not_called()
