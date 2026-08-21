#!/usr/bin/env python3
# Copyright 2026
"""Tests for the durable harness trace collector."""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import patch

from harness import trace_run


class TraceRunTest(unittest.TestCase):
    """Verify backend diagnostics keep subprocess boundaries fixed."""

    def test_request_id_remains_one_argument(self) -> None:
        """Keep shell-like request text in one child-process argument."""
        request_id = "-request; echo not-a-command"
        completed = subprocess.CompletedProcess([], 0, stdout="result", stderr="")

        with patch.object(trace_run.subprocess, "run", return_value=completed) as run:
            result = trace_run.run_backend_diagnostics(request_id, timeout_seconds=7)

        command = run.call_args.args[0]
        assert command == [
            sys.executable,
            "scripts/harness_diagnostics.py",
            f"--request-id={request_id}",
        ]
        assert "shell" not in run.call_args.kwargs
        assert result["returncode"] == 0


if __name__ == "__main__":
    unittest.main()
