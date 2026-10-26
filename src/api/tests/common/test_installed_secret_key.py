"""Check installation output against the real manual configuration consumers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import jwt
import pytest
from dotenv import dotenv_values
from flask import Flask
from flaskr.common.config import Config

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "explicit_key", [None, "fixture-'single'-\"double\"-$value-#-key"]
)
def test_saved_key_survives_manual_startup_and_reinstallation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_key: str | None
) -> None:
    """Manual restarts reuse the key and continue verifying existing JWTs."""
    output = tmp_path / ".env"
    environment = {"PATH": os.environ["PATH"]}
    if explicit_key is not None:
        environment["SECRET_KEY"] = explicit_key
    command = [
        sys.executable,
        str(ROOT / "scripts/prepare_env.py"),
        "--output",
        str(output),
    ]
    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=True
    )
    saved = output.read_bytes()
    values = dotenv_values(output)
    key = values["SECRET_KEY"]
    assert key
    if explicit_key is not None:
        assert key == explicit_key
    assert key not in first.stdout + first.stderr
    monkeypatch.setenv("SECRET_KEY", key)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite://")
    monkeypatch.setenv("LLM_MODEL_1_ID", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    app = Flask(__name__)
    app.config = Config(app.config, app)
    token = jwt.encode(
        {"user": "fixture-user"}, app.config["SECRET_KEY"], algorithm="HS256"
    )

    # A new install-time shell override must never rotate saved configuration.
    second = subprocess.run(
        command,
        env={**environment, "SECRET_KEY": "different-fixture-key"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert output.read_bytes() == saved
    assert key not in second.stdout + second.stderr
    monkeypatch.setenv("SECRET_KEY", dotenv_values(output)["SECRET_KEY"])
    restarted = Flask(__name__)
    restarted.config = Config(restarted.config, restarted)
    assert jwt.decode(token, restarted.config["SECRET_KEY"], algorithms=["HS256"]) == {
        "user": "fixture-user"
    }
