# ruff: noqa: INP001 -- Standalone repository integration tests.
"""Verify installation keys reach real Compose and manual dotenv consumers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def compose_command() -> list[str]:
    """Use an explicit standalone binary or the installed Docker CLI plugin."""
    if binary := os.environ.get("TEST_COMPOSE_BINARY"):
        return [binary]
    if docker := shutil.which("docker"):
        return [docker, "compose"]
    pytest.skip("Docker Compose is required for actual configuration rendering")


@pytest.mark.parametrize(
    ("files", "services"),
    [
        (
            ["docker-compose.latest.yml"],
            ["ai-shifu-api", "ai-shifu-celery-worker", "ai-shifu-celery-beat"],
        ),
        (
            ["docker-compose.dev.yml"],
            [
                "ai-shifu-api-dev",
                "ai-shifu-celery-worker-dev",
                "ai-shifu-celery-beat-dev",
            ],
        ),
        (
            ["docker-compose.yml", "docker-compose.secret-key.yml"],
            ["ai-shifu-api", "ai-shifu-celery-worker", "ai-shifu-celery-beat"],
        ),
    ],
)
def test_installation_key_reaches_all_backend_containers(
    tmp_path: Path, files: list[str], services: list[str]
) -> None:
    """New installations share one persisted value across container roles."""
    command = compose_command()
    for name in files:
        shutil.copy2(ROOT / "docker" / name, tmp_path)
    config = tmp_path / ".env"
    environment = {"PATH": os.environ["PATH"]}
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_env.py"), "--output", str(config)],
        env=environment,
        capture_output=True,
        check=True,
    )
    saved = config.read_bytes()
    key_line = next(
        line for line in saved.decode().splitlines() if line.startswith("SECRET_KEY=")
    )
    generated_key = key_line.split("=", 1)[1].strip("\"'")
    assert len(generated_key) >= 43
    for name in files:
        command.extend(["-f", str(tmp_path / name)])
    command.extend(["config", "--format", "json"])
    rendered = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    model = json.loads(rendered.stdout)
    for service in services:
        assert model["services"][service]["environment"]["SECRET_KEY"] == generated_key
    # Reinstall/restart consumes the exact same complete configuration.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_env.py"), "--output", str(config)],
        env=environment,
        capture_output=True,
        check=True,
    )
    assert config.read_bytes() == saved


def test_pinned_legacy_command_preserves_historical_effective_key(
    tmp_path: Path,
) -> None:
    """The opt-in overlay must not silently migrate existing pinned sessions."""
    command = compose_command()
    compose = tmp_path / "docker-compose.yml"
    shutil.copy2(ROOT / "docker/docker-compose.yml", compose)
    (tmp_path / ".env").write_text("SECRET_KEY=previously-ignored-fixture-key\n")
    result = subprocess.run(
        [*command, "-f", str(compose), "config", "--format", "json"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=True,
    )
    model = json.loads(result.stdout)
    for role in ["ai-shifu-api", "ai-shifu-celery-worker", "ai-shifu-celery-beat"]:
        # Compatibility fixture for the public value historically forced by Compose.
        assert model["services"][role]["environment"]["SECRET_KEY"] == "ai-shifu"  # noqa: S105


def test_fresh_pinned_overlay_refuses_missing_key(tmp_path: Path) -> None:
    """The fresh-install path cannot fall back to the legacy public key."""
    command = compose_command()
    for name in ["docker-compose.yml", "docker-compose.secret-key.yml"]:
        shutil.copy2(ROOT / "docker" / name, tmp_path)
        command.extend(["-f", str(tmp_path / name)])
    (tmp_path / ".env").write_text("SECRET_KEY=\n")
    result = subprocess.run(
        [*command, "config", "--format", "json"],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_template_has_no_public_authentication_key() -> None:
    """Installing by copying the template alone cannot enable a shared key."""
    template = (ROOT / "docker/.env.example.full").read_text()
    assert '\nSECRET_KEY=""\n' in template
    assert '\nSECRET_KEY="ai-shifu"\n' not in template
