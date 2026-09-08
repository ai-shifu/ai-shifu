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
        for index in range(4)
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
    assert result["model_count"] == 4
    assert result["page_count"] == 2
    assert result["unavailable_count"] == 3
    assert content.count('<th scope="col">') == 4
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
