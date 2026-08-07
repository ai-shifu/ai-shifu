"""Shared locking helpers for draft outline structural state."""

from .models import DraftShifu


def lock_shifu_for_outline_write(shifu_bid: str) -> None:
    """Serialize concurrent structural/content writes for one draft course."""
    (
        DraftShifu.query.filter(DraftShifu.shifu_bid == shifu_bid)
        .order_by(DraftShifu.id.desc())
        .with_for_update()
        .first()
    )
