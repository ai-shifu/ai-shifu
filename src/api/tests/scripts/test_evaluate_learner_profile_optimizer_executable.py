# Copyright 2026 AI-Shifu
"""Verify the learner-profile evaluator resolves the Codex executable."""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import evaluate_learner_profile_optimizer_prompt as evaluator


def test_codex_version_uses_resolved_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the checked Codex path for a version probe."""
    calls: list[list[str]] = []
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: "/trusted/codex")

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="codex-cli 1.2.3\n")

    monkeypatch.setattr(evaluator.subprocess, "run", run)

    version = vars(evaluator)["_codex_version"]()

    assert version == "codex-cli 1.2.3"
    assert calls == [["/trusted/codex", "--version"]]


def test_codex_version_preserves_missing_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the evaluator's version-probe error when Codex is absent."""
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: None)

    with pytest.raises(
        evaluator.EvaluationError,
        match="could not determine the codex CLI version",
    ):
        vars(evaluator)["_codex_version"]()


def test_codex_run_uses_resolved_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the checked Codex path for the main evaluator process."""
    commands: list[list[str]] = []
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: "/trusted/codex")
    monkeypatch.setattr(
        evaluator.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: contextlib.nullcontext(str(tmp_path)),
    )

    def run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("optimized profile", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(evaluator.subprocess, "run", run)

    result, metadata = vars(evaluator)["_run_codex"](
        system_prompt="system",
        user_message="user",
        model="gpt-test",
        timeout_seconds=10,
    )

    assert result == "optimized profile"
    assert metadata["tool_calls_observed"] is False
    assert commands[0][0] == "/trusted/codex"


def test_codex_run_preserves_missing_tool_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the evaluator's missing-CLI error before process startup."""
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        evaluator.tempfile,
        "TemporaryDirectory",
        lambda **_kwargs: contextlib.nullcontext(str(tmp_path)),
    )

    with pytest.raises(evaluator.EvaluationError, match="codex CLI is not installed"):
        vars(evaluator)["_run_codex"](
            system_prompt="system",
            user_message="user",
            model="gpt-test",
            timeout_seconds=10,
        )
