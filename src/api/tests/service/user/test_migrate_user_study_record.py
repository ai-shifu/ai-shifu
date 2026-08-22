"""Verify migrate user study record behavior."""

from flaskr.dao import db
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import LEARN_STATUS_IN_PROGRESS
from flaskr.service.shifu.consts import BLOCK_TYPE_CONTENT_VALUE
from flaskr.service.user.phone_flow import migrate_user_study_record


def _add_progress_with_block(shifu_bid: str, user_bid: str, suffix: str) -> None:
    db.session.add(
        LearnProgressRecord(
            progress_record_bid=f"progress-{suffix}",
            shifu_bid=shifu_bid,
            outline_item_bid=f"outline-{suffix}",
            user_bid=user_bid,
            status=LEARN_STATUS_IN_PROGRESS,
            deleted=0,
        )
    )
    db.session.add(
        LearnGeneratedBlock(
            generated_block_bid=f"block-{suffix}",
            progress_record_bid=f"progress-{suffix}",
            user_bid=user_bid,
            block_bid=f"block-bid-{suffix}",
            outline_item_bid=f"outline-{suffix}",
            shifu_bid=shifu_bid,
            type=BLOCK_TYPE_CONTENT_VALUE,
            role=0,
            generated_content="hello",
            position=1,
            status=1,
            deleted=0,
        )
    )
    db.session.commit()


def test_migrate_user_study_record_moves_records_and_blocks(app: object) -> None:
    shifu_bid = "shifu-migrate"
    with app.app_context():
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        _add_progress_with_block(shifu_bid, "tmp-user", "migrate-1")
        # An unrelated shifu must stay with the temporary user.
        _add_progress_with_block("shifu-other", "tmp-user", "migrate-2")
        # progress_record_bid is not unique, so a block owned by someone else
        # may share the identifier and must keep its owner.
        db.session.add(
            LearnGeneratedBlock(
                generated_block_bid="block-other-owner",
                progress_record_bid="progress-migrate-1",
                user_bid="other-user",
                block_bid="block-bid-other-owner",
                outline_item_bid="outline-migrate-1",
                shifu_bid=shifu_bid,
                type=BLOCK_TYPE_CONTENT_VALUE,
                role=0,
                generated_content="hello",
                position=1,
                status=1,
                deleted=0,
            )
        )
        db.session.commit()

        migrate_user_study_record(app, "tmp-user", "real-user", shifu_bid)
        db.session.commit()

        moved = LearnProgressRecord.query.filter_by(
            progress_record_bid="progress-migrate-1"
        ).one()
        assert moved.user_bid == "real-user"
        moved_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid="block-migrate-1"
        ).one()
        assert moved_block.user_bid == "real-user"

        other_owner_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid="block-other-owner"
        ).one()
        assert other_owner_block.user_bid == "other-user"

        untouched = LearnProgressRecord.query.filter_by(
            progress_record_bid="progress-migrate-2"
        ).one()
        assert untouched.user_bid == "tmp-user"
        untouched_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid="block-migrate-2"
        ).one()
        assert untouched_block.user_bid == "tmp-user"


def test_migrate_user_study_record_skips_outlines_already_present(app: object) -> None:
    shifu_bid = "shifu-migrate-dup"
    with app.app_context():
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        db.session.commit()

        _add_progress_with_block(shifu_bid, "tmp-user", "dup")
        db.session.add(
            LearnProgressRecord(
                progress_record_bid="progress-dup-target",
                shifu_bid=shifu_bid,
                outline_item_bid="outline-dup",
                user_bid="real-user",
                status=LEARN_STATUS_IN_PROGRESS,
                deleted=0,
            )
        )
        db.session.commit()

        migrate_user_study_record(app, "tmp-user", "real-user", shifu_bid)
        db.session.commit()

        kept = LearnProgressRecord.query.filter_by(
            progress_record_bid="progress-dup"
        ).one()
        assert kept.user_bid == "tmp-user"
        kept_block = LearnGeneratedBlock.query.filter_by(
            generated_block_bid="block-dup"
        ).one()
        assert kept_block.user_bid == "tmp-user"
