import types
import unittest

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy

import flaskr.dao as dao

if dao.db is None:
    _test_app = Flask("test-learn-record")
    _test_app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    _db = SQLAlchemy()
    _db.init_app(_test_app)
    dao.db = _db

from flaskr.i18n import _
from flaskr.service.learn.const import CONTEXT_INTERACTION_NEXT
from flaskr.service.learn.learn_dtos import BlockType
from flaskr.service.learn.learn_funcs import get_learn_record
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord
from flaskr.service.order.consts import (
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
)
from flaskr.service.shifu.consts import BLOCK_TYPE_MDINTERACTION_VALUE
from flaskr.util import generate_id


class LearnRecordFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask("learn-record-fallback")
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        dao.db.init_app(cls.app)
        with cls.app.app_context():
            dao.db.create_all()

    def setUp(self):
        self.app = self.__class__.app
        self.ctx = self.app.app_context()
        self.ctx.push()
        dao.db.session.query(LearnGeneratedBlock).delete()
        dao.db.session.query(LearnProgressRecord).delete()
        dao.db.session.commit()

    def tearDown(self):
        dao.db.session.remove()
        self.ctx.pop()

    def _create_progress(self, status: int) -> LearnProgressRecord:
        progress = LearnProgressRecord(
            progress_record_bid="progress-1",
            shifu_bid="shifu-1",
            outline_item_bid="outline-1",
            user_bid="user-1",
            status=status,
        )
        dao.db.session.add(progress)
        dao.db.session.commit()
        return progress

    def _set_request_user(self, mobile: str = ""):
        request.user = types.SimpleNamespace(mobile=mobile, user_id="user-1")

    def test_appends_virtual_button_when_completed(self):
        progress = self._create_progress(LEARN_STATUS_COMPLETED)

        with self.app.test_request_context():
            self._set_request_user()
            result = get_learn_record(
                self.app,
                progress.shifu_bid,
                progress.outline_item_bid,
                progress.user_bid,
                False,
            )

        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.block_type, BlockType.INTERACTION)
        self.assertIn(CONTEXT_INTERACTION_NEXT, record.content)

    def test_uses_persisted_button_when_present(self):
        progress = self._create_progress(LEARN_STATUS_COMPLETED)
        button_label = _("server.learn.nextChapterButton")
        button_md = f"?[{button_label}//{CONTEXT_INTERACTION_NEXT}]({button_label})"
        block = LearnGeneratedBlock(
            generated_block_bid=generate_id(self.app),
            progress_record_bid=progress.progress_record_bid,
            user_bid=progress.user_bid,
            block_bid="",
            outline_item_bid=progress.outline_item_bid,
            shifu_bid=progress.shifu_bid,
            type=BLOCK_TYPE_MDINTERACTION_VALUE,
            role=1,
            generated_content="",
            position=0,
            block_content_conf=button_md,
            status=1,
        )
        dao.db.session.add(block)
        dao.db.session.commit()

        with self.app.test_request_context():
            self._set_request_user()
            result = get_learn_record(
                self.app,
                progress.shifu_bid,
                progress.outline_item_bid,
                progress.user_bid,
                False,
            )

        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.generated_block_bid, block.generated_block_bid)
        self.assertIn(CONTEXT_INTERACTION_NEXT, record.content)

    def test_no_button_when_not_completed(self):
        progress = self._create_progress(LEARN_STATUS_IN_PROGRESS)

        with self.app.test_request_context():
            self._set_request_user()
            result = get_learn_record(
                self.app,
                progress.shifu_bid,
                progress.outline_item_bid,
                progress.user_bid,
                False,
            )

        self.assertEqual(result.records, [])


if __name__ == "__main__":
    unittest.main()
