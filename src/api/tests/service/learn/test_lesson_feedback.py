import json
import unittest

from flask import Flask
import flaskr.dao as dao

from flaskr.service.learn.lesson_feedback import (
    build_lesson_feedback_interaction_md,
    submit_lesson_feedback,
)
from flaskr.service.learn.models import (
    LearnGeneratedBlock,
    LearnLessonFeedback,
    LearnProgressRecord,
)
from flaskr.service.order.consts import LEARN_STATUS_COMPLETED
from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE


class LessonFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("lesson-feedback-tests")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_BINDS={
                "ai_shifu_saas": "sqlite:///:memory:",
                "ai_shifu_admin": "sqlite:///:memory:",
            },
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)
        with cls.app.app_context():
            dao.db.create_all()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        LearnLessonFeedback.query.delete()
        LearnGeneratedBlock.query.delete()
        LearnProgressRecord.query.delete()
        dao.db.session.commit()

    def tearDown(self):
        dao.db.session.remove()
        self.ctx.pop()

    def test_submit_feedback_upserts_single_active_row(self):
        progress = LearnProgressRecord(
            progress_record_bid="progress-1",
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            user_bid="user-1",
            status=LEARN_STATUS_COMPLETED,
        )
        dao.db.session.add(progress)
        interaction = LearnGeneratedBlock(
            generated_block_bid="block-1",
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            role=1,
            generated_content="",
            position=0,
            block_content_conf=build_lesson_feedback_interaction_md(),
            status=1,
        )
        dao.db.session.add(interaction)
        dao.db.session.commit()

        first = submit_lesson_feedback(
            self.app,
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            score=5,
            comment="Great section",
            mode="read",
        )
        second = submit_lesson_feedback(
            self.app,
            user_bid="user-1",
            shifu_bid="shifu-1",
            outline_bid="outline-1",
            score=3,
            comment="Need more examples",
            mode="listen",
        )

        rows = LearnLessonFeedback.query.filter(
            LearnLessonFeedback.user_bid == "user-1",
            LearnLessonFeedback.shifu_bid == "shifu-1",
            LearnLessonFeedback.outline_item_bid == "outline-1",
            LearnLessonFeedback.deleted == 0,
        ).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].score, 3)
        self.assertEqual(rows[0].comment, "Need more examples")
        self.assertEqual(rows[0].mode, "listen")
        self.assertEqual(rows[0].progress_record_bid, "progress-1")
        self.assertEqual(rows[0].bid, rows[0].lesson_feedback_bid)
        self.assertEqual(first["lesson_feedback_bid"], second["lesson_feedback_bid"])

        synced_block = LearnGeneratedBlock.query.filter(
            LearnGeneratedBlock.generated_block_bid == "block-1"
        ).first()
        synced_generated_content = json.loads(synced_block.generated_content)
        self.assertEqual(synced_generated_content.get("score"), 3)
        self.assertEqual(synced_generated_content.get("comment"), "Need more examples")


if __name__ == "__main__":
    unittest.main()
