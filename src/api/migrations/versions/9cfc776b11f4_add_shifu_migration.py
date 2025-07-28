"""add_shifu_migration

Revision ID: 9cfc776b11f4
Revises: d9605bb33e67
Create Date: 2025-07-18 09:41:54.833515

"""

# revision identifiers, used by Alembic.
revision = "9cfc776b11f4"
down_revision = "d9605bb33e67"
branch_labels = None
depends_on = None


def upgrade():
    from flask import current_app
    from flaskr.service.shifu.migration import migrate_shifu_draft_to_shifu_draft_v2
    from flaskr.service.lesson.models import AICourse
    from flaskr.dao import db
    import time

    old_shifu_bids = AICourse.query.with_entities(AICourse.course_id).distinct().all()

    for i, course_id in enumerate(old_shifu_bids):
        old_shifu_bid = course_id[0]
        old_course = AICourse.query.filter(AICourse.course_id == old_shifu_bid).first()

        print(
            f"migrate shifu draft to shifu draft v2, shifu_bid: {old_shifu_bid}, {old_course.course_name}, {i + 1}/{len(old_shifu_bids)}"
        )

        try:
            # 每次循环前刷新数据库连接
            db.session.close()
            db.engine.dispose()

            # 重试机制：最多重试 3 次
            max_retries = 3
            for retry in range(max_retries):
                try:
                    migrate_shifu_draft_to_shifu_draft_v2(current_app, old_shifu_bid)
                    print(f"Successfully migrated shifu_bid: {old_shifu_bid}")
                    break
                except Exception as e:
                    print(
                        f"Error migrating shifu_bid {old_shifu_bid}, attempt {retry + 1}/{max_retries}: {str(e)}"
                    )
                    if retry < max_retries - 1:
                        print("Retrying in 5 seconds...")
                        time.sleep(5)
                        # 重新建立连接
                        db.session.close()
                        db.engine.dispose()
                    else:
                        print(
                            f"Failed to migrate shifu_bid {old_shifu_bid} after {max_retries} attempts"
                        )
                        # 可以选择继续下一个还是抛出异常
                        # raise e  # 如果想中止整个迁移，取消注释这行

        except Exception as e:
            print(f"Critical error processing shifu_bid {old_shifu_bid}: {str(e)}")
            # 继续处理下一个而不是中止整个迁移
            continue


def downgrade():
    pass
