#!/usr/bin/env python3
"""Smoke-test final production images and verify the published content matches."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
API_ENV = {
    "SKIP_LOAD_DOTENV": "1",
    "PYTHON_DOTENV_DISABLED": "1",
    "SQLALCHEMY_DATABASE_URI": "sqlite:////tmp/docker-smoke.sqlite",
    "SECRET_KEY": "docker-smoke-only-placeholder",
    "LLM_MODEL_1_ID": "gpt-smoke",
    "OPENAI_API_KEY": "smoke-only-placeholder",
    "OPENAI_BASE_URL": "http://127.0.0.1:9/v1",
    "GEMINI_LIVE_ENABLED": "false",
    "REDIS_HOST": "",
    "CELERY_BROKER_URL": "memory://",
    "CELERY_RESULT_BACKEND": "cache+memory://",
}
WEB_ENV = {"PORT": "3000", "NEXT_PUBLIC_API_BASE_URL": "http://localhost:5800"}
SHARP_PROBE = """
(async () => {
  const sharp = require('sharp');
  const bytes = await sharp({ create: { width: 1, height: 1, channels: 4,
    background: { r: 255, g: 0, b: 0, alpha: 1 } } }).png().toBuffer();
  if (!bytes.length) throw new Error('Sharp produced an empty image');
  require(`@next/swc-linux-${process.arch}-musl`);
})().catch(error => { console.error(error); process.exit(1); });
"""


def docker(*arguments: str) -> str:
    """Execute Docker without evaluating image or metadata arguments in a shell."""
    result = subprocess.run(
        ["docker", *arguments], check=True, capture_output=True, text=True, timeout=180
    )
    if arguments[0] == "logs":
        return (result.stdout + result.stderr).strip()
    return result.stdout.strip()


def environment_options(values: dict[str, str]) -> list[str]:
    """Pass only isolated fixture settings into a production container."""
    return [
        option for key, value in values.items() for option in ("-e", f"{key}={value}")
    ]


def read_http(url: str) -> bytes:
    """Read a successful loopback-only response without exposing external endpoints."""
    if not url.startswith("http://127.0.0.1:"):
        message = "Smoke HTTP requests must remain on loopback"
        raise ValueError(message)
    with urlopen(url, timeout=5) as response:  # noqa: S310 -- Only the loopback HTTP origin above is accepted.
        if response.status != 200:
            message = f"Smoke HTTP response was {response.status}"
            raise ValueError(message)
        return response.read()


def validate_health(body: bytes) -> None:
    """Reject business errors that still carry HTTP 200."""
    data = json.loads(body)
    if data.get("code") != 0 or data.get("data") != "ok":
        message = "API health response does not report a healthy application"
        raise ValueError(message)


def validate_i18n(body: bytes) -> None:
    """Require a translation loaded from the final image's shared resource files."""
    data = json.loads(body)
    common = data.get("translations", {}).get("common.core", {})
    if (
        data.get("language") != "en-US"
        or data.get("missingNamespaces") != []
        or common.get("ok") != "OK"
    ):
        message = "Web shared i18n resources are missing or incorrect"
        raise ValueError(message)


def wait_for_http(url: str, timeout: float) -> bytes:
    """Wait for startup only; successful but invalid responses fail in their validator."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return read_http(url)
        except (URLError, TimeoutError, OSError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def check_dependencies(service: str, image: str) -> None:
    """Execute native modules and required service binaries in the final image."""
    if service == "web":
        docker("run", "--rm", "--entrypoint", "node", image, "-e", SHARP_PROBE)
        return
    docker(
        "run",
        "--rm",
        "--entrypoint",
        "python",
        image,
        "-c",
        "import flask, gunicorn, celery, gevent, greenlet, cryptography, orjson, pydantic_core",
    )
    docker("run", "--rm", "--entrypoint", "ffmpeg", image, "-version")
    docker("run", "--rm", "--entrypoint", "celery", image, "--version")


def loopback_origin(binding: str) -> str:
    """Require Docker's randomly allocated port to remain private to this runner."""
    if not re.fullmatch(r"127\.0\.0\.1:[0-9]+", binding):
        message = "Container port must be published only to loopback"
        raise ValueError(message)
    return f"http://{binding}"


def check_web_http(origin: str, timeout: float) -> None:
    """Exercise runtime configuration, shared translations and rendered static assets."""
    config = json.loads(wait_for_http(f"{origin}/api/config", timeout))
    if config.get("apiBaseUrl") != WEB_ENV["NEXT_PUBLIC_API_BASE_URL"]:
        message = "Web runtime API configuration was not preserved"
        raise ValueError(message)
    validate_i18n(read_http(f"{origin}/api/i18n?lng=en-US&ns=common.core"))
    if b"<svg" not in read_http(f"{origin}/logo.svg"):
        message = "Web public assets are missing"
        raise ValueError(message)
    html = read_http(f"{origin}/login").decode()
    if "<html" not in html.lower():
        message = "Web login did not render an HTML page"
        raise ValueError(message)
    asset = re.search(r"""["'](/_next/static/[^"'<>]+)["']""", html)
    if asset is None or not read_http(origin + asset[1]):
        message = "Web compiled static assets are missing"
        raise ValueError(message)


def show_container_logs(container: str) -> None:
    """Keep diagnostic collection from hiding the original smoke failure."""
    try:
        print(docker("logs", container), file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Could not collect smoke container logs: {error}", file=sys.stderr)


def smoke(
    service: str, image: str, platform: str, *, timeout: float = 120
) -> dict[str, str]:
    """Start the default production command, check responses, and always remove it."""
    inspected = json.loads(docker("image", "inspect", image))[0]
    actual = f"{inspected['Os']}/{inspected['Architecture']}"
    if actual != platform or not DIGEST.fullmatch(inspected["Id"]):
        message = "Local image platform/config digest does not match the native build"
        raise ValueError(message)
    if service == "web" and inspected.get("Config", {}).get("User") in (
        None,
        "",
        "0",
        "root",
    ):
        message = "Production Web image must run as a non-root user"
        raise ValueError(message)
    check_dependencies(service, image)
    port = "5800" if service == "api" else "3000"
    environment = API_ENV if service == "api" else WEB_ENV
    container = docker(
        "run",
        "-d",
        *environment_options(environment),
        "-p",
        f"127.0.0.1::{port}",
        image,
    )
    try:
        origin = loopback_origin(docker("port", container, f"{port}/tcp"))
        if service == "api":
            validate_health(wait_for_http(f"{origin}/health", timeout))
        else:
            check_web_http(origin, timeout)
    except Exception:
        # This container has only fixture credentials. Keep actual startup errors visible.
        show_container_logs(container)
        raise
    finally:
        docker("rm", "--force", container)
    print(f"Production smoke passed: {service} {platform}")
    return {"service": service, "platform": platform, "config_digest": inspected["Id"]}


def published_config(image: str, digest: str, platform: str) -> str:
    """Resolve the target manifest's immutable image config, including index exporters."""
    raw = json.loads(
        docker("buildx", "imagetools", "inspect", "--raw", f"{image}@{digest}")
    )
    if "manifests" in raw:
        matches = [
            item
            for item in raw["manifests"]
            if f"{item.get('platform', {}).get('os')}/{item.get('platform', {}).get('architecture')}"
            == platform
        ]
        if len(matches) != 1 or not DIGEST.fullmatch(matches[0].get("digest", "")):
            message = "Published index lacks exactly one tested platform image"
            raise ValueError(message)
        raw = json.loads(
            docker(
                "buildx",
                "imagetools",
                "inspect",
                "--raw",
                f"{image}@{matches[0]['digest']}",
            )
        )
    return raw.get("config", {}).get("digest", "")


def verify_published(
    record: dict[str, str], images: str, digest: str, *, pull_smoke: bool = False
) -> None:
    """Require every registry's published filesystem/config to match the smoke-tested image."""
    expected = record.get("config_digest", "")
    platform = record.get("platform", "")
    repositories = images.split(",")
    if (
        not DIGEST.fullmatch(expected)
        or not DIGEST.fullmatch(digest)
        or platform not in {"linux/amd64", "linux/arm64"}
        or (pull_smoke and record.get("service") not in {"api", "web"})
        or any(
            not image or "@" in image or any(c.isspace() for c in image)
            for image in repositories
        )
    ):
        message = "Invalid smoke record or publication inputs"
        raise ValueError(message)
    for image in repositories:
        if published_config(image, digest, platform) != expected:
            message = f"Published {platform} image differs from the smoke-tested image"
            raise ValueError(message)
        print(f"Verified smoke-tested content: {image} {platform}")
        if pull_smoke:
            reference = f"{image}@{digest}"
            docker("pull", "--platform", platform, reference)
            pulled = smoke(record["service"], reference, platform)
            if pulled.get("config_digest") != expected:
                message = "Registry-pulled production image differs from the original smoke config"
                raise ValueError(message)
            print(f"Verified registry-pulled production smoke: {image} {platform}")


def main() -> None:
    """Expose smoke and immutable publication verification to the packaging workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("smoke")
    check.add_argument("service", choices=("api", "web"))
    check.add_argument("image")
    check.add_argument("platform", choices=("linux/amd64", "linux/arm64"))
    check.add_argument("--record", type=Path, required=True)
    verify = commands.add_parser("verify-published")
    verify.add_argument("record", type=Path)
    verify.add_argument("digest")
    verify.add_argument("--images", required=True)
    verify.add_argument("--pull-smoke", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "smoke":
            record = smoke(args.service, args.image, args.platform)
            args.record.write_text(json.dumps(record) + "\n")
        else:
            verify_published(
                json.loads(args.record.read_text()),
                args.images,
                args.digest,
                pull_smoke=args.pull_smoke,
            )
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
