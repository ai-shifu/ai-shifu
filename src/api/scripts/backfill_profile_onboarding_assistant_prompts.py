"""Backfill saved profile-onboarding assistant prompts for a new locale."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure src/api is importable when this script is run by path.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Import the app factory without creating a second application at import time.
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")


def main() -> int:
    """Preview or apply an idempotent prompt backfill for one locale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locale",
        default="es-ES",
        help="Supported locale to backfill (default: es-ES for existing scripts)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Generate and publish missing prompts; omission previews only",
    )
    args = parser.parse_args()

    from app import create_app
    from flaskr.service.common.profile_onboarding import (
        backfill_profile_onboarding_assistant_locale,
    )

    app = create_app(serving_http=False)
    with app.app_context():
        result = backfill_profile_onboarding_assistant_locale(
            app,
            locale=args.locale,
            apply=args.apply,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
