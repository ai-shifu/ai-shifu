"""Audited, repeatable cleanup of historical course default selections."""

from __future__ import annotations

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.shifu.models import (
    DraftShifu,
    ModelTierMigrationAudit,
    PublishedShifu,
)
from flaskr.util.datetime import now_utc, to_utc_iso
from flaskr.util.uuid import generate_id
from sqlalchemy.orm import load_only

_MIGRATION_PAGE_SIZE = 500


def migrate_default_model_tiers(app: object, *, apply: bool = False) -> dict:
    """Backfill only blank course selections, including historical revisions."""
    batch_bid = generate_id(app)
    created_at = now_utc()
    changes = []
    # ORM whitespace checks include tabs/newlines, not just SQL TRIM spaces.
    with unit_of_work():
        for model_type in (DraftShifu, PublishedShifu):
            query = model_type.query.options(
                load_only(
                    model_type.id,
                    model_type.llm,
                    model_type.ask_llm,
                    model_type.updated_at,
                )
            ).order_by(model_type.id)
            if apply:
                query = query.with_for_update()
            last_id = 0
            while True:
                records = (
                    query.filter(model_type.id > last_id)
                    .limit(_MIGRATION_PAGE_SIZE)
                    .all()
                )
                if not records:
                    break
                last_id = records[-1].id
                for record in records:
                    for field in ("llm", "ask_llm"):
                        previous_model = getattr(record, field)
                        if str(previous_model or "").strip():
                            continue
                        changes.append(
                            {
                                "table": model_type.__tablename__,
                                "row_id": record.id,
                                "field": field,
                            }
                        )
                        if apply:
                            # Updating a model selection must not alter the
                            # authoring revision's original modification timestamp.
                            db.session.execute(
                                db.update(model_type)
                                .where(model_type.id == record.id)
                                .values(
                                    **{
                                        field: "fast",
                                        "updated_at": record.updated_at,
                                    }
                                )
                            )
                            db.session.add(
                                ModelTierMigrationAudit(
                                    batch_bid=batch_bid,
                                    table_name=model_type.__tablename__,
                                    row_id=record.id,
                                    field_name=field,
                                    previous_model=previous_model,
                                    new_model="fast",
                                    created_at=created_at,
                                )
                            )
                # Flush pending audits before fetching the next bounded page.
                if apply:
                    db.session.flush()
    return {
        "batch_bid": batch_bid,
        "created_at": to_utc_iso(created_at),
        "applied": apply,
        "count": len(changes),
        "changes": changes,
    }
