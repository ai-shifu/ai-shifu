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
    from alembic import op
    from sqlalchemy import text
    import time

    old_shifu_bids = AICourse.query.with_entities(AICourse.course_id).distinct().all()
    connection = op.get_bind()
    for i, course_id in enumerate(old_shifu_bids):
        old_shifu_bid = course_id[0]
        old_course = AICourse.query.filter(AICourse.course_id == old_shifu_bid).first()
        print(
<<<<<<< HEAD
            f"migrate shifu draft to shifu draft v2, shifu_bid: {old_shifu_bid}, {old_course.course_name}, {i + 1}/{len(old_shifu_bids)}"
=======
            f"migrate shifu draft to shifu draft v2, shifu_bid: {old_shifu_bid}, {old_course.course_name}, {i+1}/{len(old_shifu_bids)}"
>>>>>>> 6d36e6e1 (fix: migration error on phone-input or checkcode-input blocks (#658))
        )

        try:
            # close session and dispose engine before migrate

            max_retries = 3
            for retry in range(max_retries):
                try:
                    connection.execute(text("SELECT now()"))
                    migrate_shifu_draft_to_shifu_draft_v2(current_app, old_shifu_bid)
                    print(f"Successfully migrated shifu_bid: {old_shifu_bid}")
                    break
                except Exception as e:
                    print(
                        f"Error migrating shifu_bid {old_shifu_bid}, attempt {retry + 1}/{max_retries}: {str(e)}"
                    )
                    if retry < max_retries - 1:
                        print("Retrying in 5 seconds...")
                        db.session.close()
                        db.engine.dispose()
                        time.sleep(5)
                    else:
                        print(
                            f"Failed to migrate shifu_bid {old_shifu_bid} after {max_retries} attempts"
                        )

        except Exception as e:
            print(f"Critical error processing shifu_bid {old_shifu_bid}: {str(e)}")
            continue

    print(
        "All migrations completed, refreshing database connection for alembic version update..."
    )
    try:
        db.session.close()
        db.engine.dispose()
        connection.execute(text("SELECT now()"))
        print("Database connection refreshed successfully")
    except Exception as e:
        print(f"Warning: Error refreshing database connection: {str(e)}")


def downgrade():
    pass
