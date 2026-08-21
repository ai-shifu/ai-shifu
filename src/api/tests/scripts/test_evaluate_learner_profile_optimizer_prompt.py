# Copyright 2026
"""Verify the learner-profile prompt evaluator subprocess boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from scripts import evaluate_learner_profile_optimizer_prompt as evaluator

if TYPE_CHECKING:
    import pytest


def test_run_codex_keeps_dynamic_values_as_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep prompt, model, and learner text out of the executable position."""
    captured_command: list[str] = []
    captured_kwargs: dict[str, object] = {}

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        captured_kwargs.update(kwargs)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text("optimized profile", encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"turn.completed","usage":{}}\n',
            stderr="",
        )

    temporary_directory = MagicMock()
    temporary_directory.return_value.__enter__.return_value = str(tmp_path)
    monkeypatch.setattr(evaluator.tempfile, "TemporaryDirectory", temporary_directory)
    monkeypatch.setattr(evaluator.shutil, "which", lambda _name: "/trusted/codex")
    monkeypatch.setattr(evaluator.subprocess, "run", fake_run)

    # Exercise the internal runner without widening the production script API.
    run_codex = vars(evaluator)["_run_codex"]
    result, metadata = run_codex(
        system_prompt='Keep "quoted" text; do not execute it.',
        user_message="profile; echo not-a-command",
        model="test-model",
        timeout_seconds=5,
    )

    assert captured_command[0] == "/trusted/codex"
    assert captured_command[captured_command.index("--model") + 1] == "test-model"
    assert captured_kwargs["input"] == "profile; echo not-a-command"
    assert "shell" not in captured_kwargs
    assert result == "optimized profile"
    assert metadata["tool_calls_observed"] is False
