"""Verify the retirement CLI's cutover guards and reconciliation exit codes."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from flaskr.service.tts import clone_job_retirement
from scripts.retire_minimax_clone_jobs import main


def test_apply_requires_stopped_workers_before_loading_application(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected_app_load(**_kwargs: object) -> None:
        pytest.fail("The application must not load without the cutover acknowledgement")

    monkeypatch.setitem(
        sys.modules, "app", SimpleNamespace(create_app=unexpected_app_load)
    )
    with pytest.raises(SystemExit) as error:
        main(["--apply"])
    assert error.value.code == 2
    assert "--workers-stopped" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "captured", "manual", "expected_exit"),
    [
        ([], 0, 0, 0),
        (["--apply", "--workers-stopped"], 0, 0, 0),
        (["--apply", "--workers-stopped"], 1, 0, 1),
        ([], 0, 1, 1),
    ],
)
def test_cli_outputs_report_and_blocks_unresolved_cutover(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    captured: int,
    manual: int,
    expected_exit: int,
) -> None:
    app = object()
    app_options: list[dict[str, object]] = []
    calls: list[dict[str, object]] = []
    result = {"captured_count": captured, "manual_review_count": manual, "jobs": []}

    def create_app(**kwargs: object) -> object:
        app_options.append(kwargs)
        return app

    def retire(supplied_app: object, **kwargs: object) -> dict[str, object]:
        assert supplied_app is app
        calls.append(kwargs)
        return result

    monkeypatch.setitem(sys.modules, "app", SimpleNamespace(create_app=create_app))
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(clone_job_retirement, "retire_minimax_clone_jobs", retire)

    assert main(argv) == expected_exit
    assert app_options == [{"serving_http": False}]
    assert calls == [
        {"apply": "--apply" in argv, "workers_stopped": "--workers-stopped" in argv}
    ]
    assert json.loads(capsys.readouterr().out) == result
