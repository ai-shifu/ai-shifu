"""Ensure third-party dotenv loading cannot import developer configuration."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


def test_transitive_dotenv_loader_cannot_override_test_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "BACKEND_TEST_DOTENV_SENTINEL"
    monkeypatch.delenv(key, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{key}=unexpected\n", encoding="utf-8")

    assert load_dotenv(dotenv_path=dotenv, override=True) is False
    assert key not in os.environ
