from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure `src/api` is on sys.path when executed as a file path.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Avoid side-effectful app auto-creation on import.
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill learn_generated_elements from markdown-flow generated blocks only",
    )
    parser.add_argument(
        "--progress-record-bid",
        action="append",
        dest="progress_record_bids",
        default=[],
        help="Specific progress_record_bid to backfill; repeatable",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Resume from learn_progress_records.id greater than this value",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of progress records to process when --progress-record-bid is not used",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Replace active learn_generated_elements rows for matched progress records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and report backfill results without writing learn_generated_elements",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.progress_record_bids and args.limit <= 0:
        parser.error(
            "--limit must be greater than 0 when --progress-record-bid is not provided"
        )

    app = create_app()
    from flaskr.service.learn.listen_elements import (
        backfill_learn_generated_elements_batch,
    )

    with app.app_context():
        batch_result = backfill_learn_generated_elements_batch(
            app,
            progress_record_bids=args.progress_record_bids or None,
            after_id=args.after_id,
            limit=args.limit,
            overwrite=args.overwrite_existing,
            dry_run=args.dry_run,
        )

    print(json.dumps(batch_result.as_dict(), ensure_ascii=False, indent=2))
    return 1 if batch_result.failed_progress_records else 0


if __name__ == "__main__":
    raise SystemExit(main())
