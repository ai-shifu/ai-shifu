"""Fit a reviewed course-completion credit artifact from screened offline data.

Run from ``src/api`` with ``python -m scripts.calibrate_course_completion_credits``.
The input is a private, read-only export in the candidate schema documented by
``course_completion_credit_samples.py``. This command never opens a database or
prints raw learner/course content. It writes an artifact only when at least one
engine/language group passes every release gate.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from flaskr.service.shifu.admin_operations.course_completion_credit_model import (
    DEFAULT_ARTIFACT_PATH,
    fit_calibration_groups,
)

from scripts.course_completion_credit_samples import screen_bundle

if TYPE_CHECKING:
    from collections.abc import Sequence


def calibrate_file(
    input_path: Path, *, version: str, output_path: Path, dry_run: bool = False
) -> dict[str, object]:
    """Screen and fit one private export, returning only aggregate diagnostics."""
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    samples, excluded = screen_bundle(payload)
    artifact = fit_calibration_groups(samples, version=version)
    group_reports = {
        key: {
            "sample_count": group["sample_count"],
            "course_count": group["course_count"],
            "validation": group["validation"],
        }
        for key, group in artifact["groups"].items()
    }
    report: dict[str, object] = {
        "accepted_samples": len(samples),
        "excluded": excluded,
        "qualified_groups": group_reports,
        "rejected_groups": artifact["rejected_groups"],
        "artifact_written": False,
    }
    if not artifact["groups"] or dry_run:
        return report

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_path.parent) as temporary_dir:
        staging = Path(temporary_dir) / output_path.name
        staging.write_text(
            json.dumps(artifact, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staging.replace(output_path)
    report["artifact_written"] = True
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Validate an offline export and optionally install its gated artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Private offline candidate JSON")
    parser.add_argument("--version", required=True, help="Calibration artifact version")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARTIFACT_PATH,
        help="Validated artifact output path",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    report = calibrate_file(
        args.input,
        version=args.version,
        output_path=args.output,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if report["qualified_groups"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
