"""The calibration command must not publish an unqualified estimate."""

import json
from pathlib import Path

from scripts.calibrate_course_completion_credits import calibrate_file


def test_missing_historical_evidence_cannot_install_an_artifact(tmp_path: Path) -> None:
    source = tmp_path / "candidates.json"
    target = tmp_path / "calibration.json"
    source.write_text(json.dumps({"candidates": [{}]}), encoding="utf-8")

    report = calibrate_file(source, version="v1", output_path=target)

    assert report["accepted_samples"] == 0
    assert report["qualified_groups"] == {}
    assert report["artifact_written"] is False
    assert not target.exists()
