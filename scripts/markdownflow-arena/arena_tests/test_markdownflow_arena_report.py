"""Verify offline rendering, failed-model cells, and untrusted content boundaries."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from markdownflow_arena_lib.report import write_report
from markdownflow_arena_lib.state import ArenaError, artifact_id


@pytest.fixture
def report_manifest(tmp_path: Path) -> dict:
    models = [
        {"requested": f"model-{index}", "model": f"provider/model-{index}"}
        for index in range(5)
    ]
    case = {
        "case_id": "slides",
        "category": "slides",
        "input_hash": "fixed",
        "source": {
            "course_title": "Course",
            "outline_title": '<script>alert("title")</script>',
        },
        "document": 'Create slides about </pre><script>alert("prompt")</script>',
        "document_prompt": "Use short labels.",
        "block_index": 0,
    }
    pages = [tmp_path / f"page-{index}.png" for index in range(2)]
    for index, page in enumerate(pages):
        page.write_bytes(b"synthetic PNG" + bytes([index]))
    artifact = {
        "status": "complete",
        "elements": [{"is_marker": True}, {"is_marker": True}],
        "render": {
            "pages": list(map(str, pages)),
            "sha256": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in pages
            },
        },
        "metadata": {"elapsed_ms": 1000},
    }
    return {
        "models": models,
        "cases": [case, {"case_id": "text", "category": "text"}],
        "artifacts": {
            artifact_id(case, models[0]): artifact,
            artifact_id(case, models[1]): {"status": "complete", "elements": []},
            artifact_id(case, models[2]): {"status": "truncated"},
        },
    }


def test_report_has_all_columns_pages_and_failure_cells(
    report_manifest: dict, tmp_path: Path
) -> None:
    result = write_report(report_manifest, tmp_path)
    output = Path(result["path"])
    content = output.read_text()
    assert result["case_count"] == 1
    assert result["model_count"] == 5
    assert result["page_count"] == 2
    assert result["unavailable_count"] == 4
    assert content.count('<th scope="col">') == 5
    assert content.count("<tbody data-case=") == 1
    assert content.count('src="data:image/png;base64,') == 2
    assert 'href="http' not in content
    assert 'src="http' not in content
    assert "no_slides" not in content
    assert output.stat().st_mode & 0o777 == 0o600
    assert "<script>alert(" not in content
    assert "&lt;script&gt;alert(" in content
    assert "default-src 'none'" in content
    assert "provider/model-3" in content


def test_report_rebuild_replaces_previous_page(
    report_manifest: dict, tmp_path: Path
) -> None:
    result = write_report(report_manifest, tmp_path)
    before = Path(result["path"]).read_bytes()
    assert write_report(report_manifest, tmp_path)["path"] == result["path"]
    assert Path(result["path"]).read_bytes() == before


@pytest.mark.parametrize("attack", ["modified", "outside"])
def test_report_rejects_unverified_image_and_preserves_previous_report(
    report_manifest: dict, tmp_path: Path, attack: str
) -> None:
    output = tmp_path / "comparison.html"
    output.write_text("Previous verified report")
    artifact = next(iter(report_manifest["artifacts"].values()))
    if attack == "modified":
        Path(artifact["render"]["pages"][0]).write_bytes(b"modified")
    else:
        artifact["render"]["pages"][0] = "/etc/passwd"
    with pytest.raises(ArenaError):
        write_report(report_manifest, tmp_path)
    assert output.read_text() == "Previous verified report"


def test_recorded_performance_aggregates_calls_without_inventing_missing_values() -> (
    None
):
    from markdownflow_arena_lib.report import performance

    metrics = performance(
        {
            "metadata": {
                "elapsed_ms": 5000,
                "requests": [
                    {
                        "latency_ms": 1000,
                        "usage": {"input": 100, "output": 20},
                        "input_cache_tokens": 0,
                    },
                    {
                        "latency_ms": 2000,
                        "usage": {"input": 200, "output": 40},
                        "input_cache_tokens": 50,
                    },
                ],
            }
        }
    )
    assert metrics == {
        "elapsed": 5,
        "latency": 3,
        "input": 300,
        "output": 60,
        "cache": 50,
        "speed": 20,
    }
    missing = performance(
        {
            "metadata": {
                "requests": [
                    {"latency_ms": 1000, "usage": {"input": 100, "output": 20}},
                    {"latency_ms": 2000, "usage": None},
                ]
            }
        }
    )
    assert missing == {
        "elapsed": None,
        "latency": 3,
        "input": None,
        "output": None,
        "cache": None,
        "speed": None,
    }


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), float("inf"), "200"])
def test_invalid_performance_is_unknown(value: object) -> None:
    from markdownflow_arena_lib.report import performance

    metrics = performance(
        {
            "metadata": {
                "elapsed_ms": value,
                "requests": [
                    {
                        "latency_ms": value,
                        "usage": {"input": value, "output": value},
                        "input_cache_tokens": value,
                    }
                ],
            }
        }
    )
    assert all(metric is None for metric in metrics.values())


def test_zero_usage_is_recorded_but_zero_duration_has_no_speed() -> None:
    from markdownflow_arena_lib.report import performance

    metrics = performance(
        {
            "metadata": {
                "elapsed_ms": 0,
                "requests": [
                    {
                        "latency_ms": 0,
                        "usage": {"input": 0, "output": 0},
                        "input_cache_tokens": 0,
                    }
                ],
            }
        }
    )
    assert metrics["output"] == 0
    assert metrics["elapsed"] == 0
    assert metrics["speed"] is None


def test_blind_headers_have_stable_codes_and_reveal_after_the_last_row(
    report_manifest: dict, tmp_path: Path
) -> None:
    import re

    result = write_report(report_manifest, tmp_path)
    content = Path(result["path"]).read_text()
    assert re.findall(r'<span class="model-code">(.*?)</span>', content) == list(
        "ABCDE"
    )
    hidden_names = r'<span class="model-name" hidden>(.*?)</span>'
    names = re.findall(hidden_names, content)
    assert len(names) == 5
    assert content.count('<dl class="performance">') == 5
    assert 'aria-expanded="false"' in content
    assert content.index('id="reveal-models"') > content.index("</main>")
    report_manifest["models"].reverse()
    write_report(report_manifest, tmp_path)
    assert re.findall(hidden_names, Path(result["path"]).read_text()) == names


def test_report_command_accepts_historical_model_roster_without_backend_calls(
    report_manifest: dict,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    import sys

    import markdownflow_arena
    from markdownflow_arena_lib.pipeline import WorkerBackend
    from markdownflow_arena_lib.state import write_json

    report_manifest["models"] = report_manifest["models"][:4]
    report_manifest.update(
        schema_version=1,
        run_id="legacy",
        status="partial",
        config={"models": [model["requested"] for model in report_manifest["models"]]},
    )
    write_json(tmp_path / "manifest.json", report_manifest)

    def fail(*_args: object, **_kwargs: object) -> None:
        message = "Report must not call the backend"
        raise AssertionError(message)

    monkeypatch.setattr(WorkerBackend, "call", fail)
    monkeypatch.setattr(
        sys, "argv", ["markdownflow_arena", "report", "--run-dir", str(tmp_path)]
    )
    assert markdownflow_arena.main() == 0
    assert json.loads(capsys.readouterr().out)["report"]["model_count"] == 4
