#!/usr/bin/env python3
"""Protect production smoke failures and the exact tested-image publication gate."""

from __future__ import annotations

import io
import json
import shutil
import ssl
import subprocess
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest
from check_docker_image import (
    API_TRUST_PROBE,
    TRUSTED_CONTROL,
    UNTRUSTED_ROOTS,
    WEB_TRUST_PROBE,
    docker,
    smoke,
    validate_health,
    validate_i18n,
    validate_trust_stores,
    verify_published,
)

CONFIG = "sha256:" + "a" * 64
MANIFEST = "sha256:" + "b" * 64
TRUST_FIXTURES = Path(__file__).parent / "testdata/image_trust"


@pytest.mark.parametrize("insecure_store", [None, "system", "certifi", "pip"])
def test_python_probe_checks_each_real_openssl_store(
    tmp_path: Path, insecure_store: str | None
) -> None:
    """Adding a distrusted public root to any independent bundle must fail smoke."""
    safe = (TRUST_FIXTURES / "isrg-root-x1.pem").read_text()
    unsafe = safe + (TRUST_FIXTURES / "emsign-ecc-root-g3.pem").read_text()
    paths = {}
    for name in ("system", "certifi", "pip"):
        paths[name] = tmp_path / f"{name}.pem"
        paths[name].write_text(unsafe if name == insecure_store else safe)
    # The probe still loads/parses the real PEM files through OpenSSL. Only the
    # package locations and the host's unrelated default CA path are redirected.
    certifi = types.ModuleType("certifi")
    certifi.where = lambda: str(paths["certifi"])
    pip_certifi = types.ModuleType("pip._vendor.certifi")
    pip_certifi.where = lambda: str(paths["pip"])
    vendor = types.ModuleType("pip._vendor")
    vendor.certifi = pip_certifi
    pip = types.ModuleType("pip")
    pip._vendor = vendor
    create_context = ssl.create_default_context
    report = io.StringIO()
    with (
        patch.dict(
            "sys.modules",
            {
                "certifi": certifi,
                "pip": pip,
                "pip._vendor": vendor,
                "pip._vendor.certifi": pip_certifi,
            },
        ),
        patch(
            "ssl.create_default_context",
            side_effect=lambda *, cafile=None: create_context(
                cafile=cafile or paths["system"]
            ),
        ),
        redirect_stdout(report),
    ):
        exec(API_TRUST_PROBE, {})  # noqa: S102 -- Execute the same fixed probe used inside the final image.
    if insecure_store:
        with pytest.raises(
            ValueError, match=f"{insecure_store} trust store.*distrusted"
        ):
            validate_trust_stores(report.getvalue(), set(paths))
    else:
        validate_trust_stores(report.getvalue(), set(paths))


@pytest.mark.parametrize("insecure_store", [None, "bundled", "default", "system"])
def test_node_probe_hashes_real_certificates_in_each_store(
    insecure_store: str | None,
) -> None:
    """Node's X509 parser must detect the same root in built-in and system stores."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to execute the final-image TLS probe")
    safe = (TRUST_FIXTURES / "isrg-root-x1.pem").read_text()
    unsafe = (TRUST_FIXTURES / "emsign-ecc-root-g3.pem").read_text()
    stores = {
        name: [safe, unsafe] if name == insecure_store else [safe]
        for name in ("bundled", "default", "system")
    }
    script = (
        "const stores = "
        + json.dumps(stores)
        + ";\n"
        + """
const realRequire = require;
const fixtureRequire = name => {
  if (name === 'node:tls') return {
    rootCertificates: stores.bundled,
    getCACertificates: () => stores.default,
  };
  if (name === 'node:fs') return {readFileSync: () => stores.system.join('\\n')};
  return realRequire(name);
};
"""
        + "new Function('require', "
        + json.dumps(WEB_TRUST_PROBE)
        + ")(fixtureRequire);"
    )
    report = subprocess.check_output([node, "-e", script], text=True)
    if insecure_store:
        with pytest.raises(
            ValueError, match=f"{insecure_store} trust store.*distrusted"
        ):
            validate_trust_stores(report, set(stores))
    else:
        validate_trust_stores(report, set(stores))


def test_trust_check_requires_every_store_and_a_positive_control() -> None:
    """Empty, missing and unsafe trust reports cannot masquerade as successful smoke."""
    with pytest.raises(ValueError, match="missing a required"):
        validate_trust_stores("{}", {"system"})
    with pytest.raises(ValueError, match="trusted control"):
        validate_trust_stores('{"system":[]}', {"system"})
    for fingerprint in UNTRUSTED_ROOTS:
        with pytest.raises(ValueError, match="distrusted root"):
            validate_trust_stores(
                json.dumps({"system": [TRUSTED_CONTROL, fingerprint]}), {"system"}
            )


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
        if args[-1] in (API_TRUST_PROBE, WEB_TRUST_PROBE):
            names = (
                ("system", "certifi", "pip")
                if args[-1] == API_TRUST_PROBE
                else ("bundled", "default", "system")
            )
            return json.dumps({name: [TRUSTED_CONTROL] for name in names})
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

    def test_distrusted_final_image_never_starts_the_application(self) -> None:
        """Trust validation must gate startup for both final image types."""
        for service in ("api", "web"):

            def insecure_docker(*args: str) -> str:
                result = self.docker(*args)
                if args[-1] in (API_TRUST_PROBE, WEB_TRUST_PROBE):
                    stores = json.loads(result)
                    stores["system"].append(next(iter(UNTRUSTED_ROOTS)))
                    return json.dumps(stores)
                return result

            with (
                patch(
                    "check_docker_image.docker", side_effect=insecure_docker
                ) as daemon,
                pytest.raises(ValueError, match=r"system trust store.*distrusted"),
            ):
                smoke(service, f"local:{service}", "linux/amd64")
            assert not any(
                call.args[:2] == ("run", "-d") for call in daemon.call_args_list
            )

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
