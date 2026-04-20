from __future__ import annotations

import argparse
import os
from decimal import Decimal

from sqlalchemy import func


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0"
    normalized = value.quantize(Decimal("0.01"))
    text = f"{normalized:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate promo campaign migration consistency."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max rows to print for each mismatch sample.",
    )
    args = parser.parse_args()

    os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")
    from app import create_app
    from flaskr.dao import db
    from flaskr.service.active.models import Active, ActiveUserRecord
    from flaskr.service.promo.models import PromoCampaign, PromoRedemption

    app = create_app()
    with app.app_context():
        has_issues = False

        print("== Counts ==")
        print(f"active: {Active.query.count()}")
        print(f"promo_promos: {PromoCampaign.query.count()}")
        print(f"active_user_record: {ActiveUserRecord.query.count()}")
        print(f"promo_redemptions: {PromoRedemption.query.count()}")
        print()

        print("== Aggregates ==")
        active_sum = db.session.query(func.sum(ActiveUserRecord.price)).scalar()
        app_sum = db.session.query(func.sum(PromoRedemption.discount_amount)).scalar()
        print(f"sum(active_user_record.price): {_format_decimal(active_sum)}")
        print(f"sum(promo_redemptions.discount_amount): {_format_decimal(app_sum)}")
        print()

        print("== Missing promos (active -> promo_promos) ==")
        missing_campaigns = (
            db.session.query(Active.active_id)
            .outerjoin(PromoCampaign, PromoCampaign.promo_bid == Active.active_id)
            .filter(PromoCampaign.promo_bid.is_(None))
            .limit(args.limit)
            .all()
        )
        if missing_campaigns:
            has_issues = True
            for (active_id,) in missing_campaigns:
                print(f"- {active_id}")
        else:
            print("OK")
        print()

        print("== Missing redemptions (active_user_record -> promo_redemptions) ==")
        missing_applications = (
            db.session.query(ActiveUserRecord.record_id)
            .outerjoin(
                PromoRedemption,
                PromoRedemption.redemption_bid == ActiveUserRecord.record_id,
            )
            .filter(PromoRedemption.redemption_bid.is_(None))
            .limit(args.limit)
            .all()
        )
        if missing_applications:
            has_issues = True
            for (record_id,) in missing_applications:
                print(f"- {record_id}")
        else:
            print("OK")
        print()

        print(
            "== Potential source duplicates (active_user_record order_id + active_id) =="
        )
        duplicates = (
            db.session.query(
                ActiveUserRecord.order_id,
                ActiveUserRecord.active_id,
                func.count(ActiveUserRecord.id),
            )
            .group_by(ActiveUserRecord.order_id, ActiveUserRecord.active_id)
            .having(func.count(ActiveUserRecord.id) > 1)
            .order_by(func.count(ActiveUserRecord.id).desc())
            .limit(args.limit)
            .all()
        )
        if duplicates:
            has_issues = True
            for order_id, active_id, cnt in duplicates:
                print(f"- order_id={order_id} active_id={active_id} count={cnt}")
        else:
            print("OK")

    return 1 if has_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
