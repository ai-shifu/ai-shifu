"""Preview or reconcile jobs before deploying the MiniMax clone removal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run the operator-only cutover command; default to a read-only preview."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Persist job cancellations and refunds"
    )
    parser.add_argument(
        "--workers-stopped",
        action="store_true",
        help="Acknowledge that all old API instances and clone workers are stopped",
    )
    args = parser.parse_args(argv)
    if args.apply and not args.workers_stopped:
        parser.error(
            "--apply requires --workers-stopped; stop old API instances and workers first"
        )

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app
    from flaskr.service.tts.clone_job_retirement import retire_minimax_clone_jobs

    app = create_app(serving_http=False)
    result = retire_minimax_clone_jobs(
        app, apply=args.apply, workers_stopped=args.workers_stopped
    )
    print(json.dumps(result, indent=2))
    # Captured unfinished jobs require an operator decision, not a refund.
    return 1 if result["captured_count"] or result["manual_review_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
