from __future__ import annotations

import argparse
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
        description=(
            "Grant white-label (custom domain + branding) to a creator by "
            "writing the manual billing entitlement and a verified domain "
            "binding. This is the fast-path operator tool for onboarding a "
            "single customer."
        ),
    )
    parser.add_argument(
        "--creator-bid",
        required=True,
        help="Creator user business identifier to grant white-label to",
    )
    parser.add_argument(
        "--host",
        default="",
        help="Custom domain host to bind and mark verified (e.g. learn.acme.com)",
    )
    parser.add_argument("--logo-wide-url", default=None, help="Wide logo URL")
    parser.add_argument("--logo-square-url", default=None, help="Square logo URL")
    parser.add_argument("--favicon-url", default=None, help="Favicon URL")
    parser.add_argument("--home-url", default=None, help="Home URL (logo click target)")
    parser.add_argument("--contact-us-url", default=None, help="Contact-us URL")
    parser.add_argument(
        "--no-custom-domain",
        action="store_true",
        help="Only grant branding; skip custom-domain entitlement and binding",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the intended changes without writing to the database",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    branding = {
        "logo_wide_url": args.logo_wide_url,
        "logo_square_url": args.logo_square_url,
        "favicon_url": args.favicon_url,
        "home_url": args.home_url,
        "contact_us_url": args.contact_us_url,
    }
    branding = {key: value for key, value in branding.items() if value is not None}
    custom_domain_enabled = not args.no_custom_domain
    will_bind_host = bool(args.host) and custom_domain_enabled

    if args.dry_run:
        print("[dry-run] no database writes will be performed")
        print(f"  creator_bid          = {args.creator_bid}")
        print("  branding_enabled     = True")
        print(f"  custom_domain_enabled= {custom_domain_enabled}")
        print(f"  branding payload     = {branding or '(unchanged)'}")
        print(f"  bind+verify host     = {args.host if will_bind_host else '(none)'}")
        return 0

    app = create_app()

    from flaskr.service.billing.domains import manage_creator_domain_binding
    from flaskr.service.billing.entitlements import grant_creator_manual_entitlement

    with app.app_context():
        state = grant_creator_manual_entitlement(
            app,
            args.creator_bid,
            branding_enabled=True,
            custom_domain_enabled=custom_domain_enabled,
            branding=branding or None,
        )
        print("entitlement granted:")
        print(f"  creator_bid           = {state.creator_bid}")
        print(f"  branding_enabled      = {state.branding_enabled}")
        print(f"  custom_domain_enabled = {state.custom_domain_enabled}")

        if will_bind_host:
            bind_result = manage_creator_domain_binding(
                app,
                args.creator_bid,
                {"action": "bind", "host": args.host},
            )
            token = bind_result.binding.verification_token
            verify_result = manage_creator_domain_binding(
                app,
                args.creator_bid,
                {
                    "action": "verify",
                    "host": args.host,
                    "verification_token": token,
                },
            )
            binding = verify_result.binding
            print("domain binding:")
            print(f"  host        = {binding.host}")
            print(f"  status      = {binding.status}")
            print(f"  ssl_status  = {binding.ssl_status}")
        elif args.host and not custom_domain_enabled:
            print(
                "skipped domain binding: custom domain disabled by --no-custom-domain"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
