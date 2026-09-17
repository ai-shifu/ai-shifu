"""The per-course setting that picks which MarkdownFlow runtime teaches a lesson."""

from __future__ import annotations

import pytest
from flaskr.dao import db
from flaskr.service.shifu.consts import (
    FLOW_ENGINE_DEFAULT,
    FLOW_ENGINE_V1,
    FLOW_ENGINE_V2,
    FLOW_ENGINE_VALUES,
)
from flaskr.service.shifu.models import DraftShifu, PublishedShifu

SHIFU = "course-under-test"


@pytest.fixture(autouse=True)
def _clean(app: object):  # noqa: ANN202 - pytest fixture
    with app.app_context():
        DraftShifu.query.filter_by(shifu_bid=SHIFU).delete()
        PublishedShifu.query.filter_by(shifu_bid=SHIFU).delete()
        db.session.commit()
        yield
        DraftShifu.query.filter_by(shifu_bid=SHIFU).delete()
        PublishedShifu.query.filter_by(shifu_bid=SHIFU).delete()
        db.session.commit()


def test_the_default_is_the_existing_runtime(app: object) -> None:
    """Every course that exists today keeps behaving exactly as it does today."""
    with app.app_context():
        draft = DraftShifu(shifu_bid=SHIFU, title="t")
        db.session.add(draft)
        db.session.commit()

        assert draft.flow_engine == FLOW_ENGINE_V1
        assert FLOW_ENGINE_DEFAULT == FLOW_ENGINE_V1


def test_both_runtimes_are_the_only_accepted_values() -> None:
    assert FLOW_ENGINE_VALUES == (FLOW_ENGINE_V1, FLOW_ENGINE_V2)
    assert FLOW_ENGINE_V1 != FLOW_ENGINE_V2


def test_the_published_row_carries_its_own_setting(app: object) -> None:
    """Learners run the published row, so the column has to exist on both tables."""
    with app.app_context():
        published = PublishedShifu(
            shifu_bid=SHIFU, title="t", flow_engine=FLOW_ENGINE_V2
        )
        db.session.add(published)
        db.session.commit()

        stored = PublishedShifu.query.filter_by(shifu_bid=SHIFU).one()
        assert stored.flow_engine == FLOW_ENGINE_V2


def test_a_draft_can_hold_either_runtime(app: object) -> None:
    with app.app_context():
        draft = DraftShifu(shifu_bid=SHIFU, title="t", flow_engine=FLOW_ENGINE_V2)
        db.session.add(draft)
        db.session.commit()

        assert DraftShifu.query.filter_by(shifu_bid=SHIFU).one().flow_engine == (
            FLOW_ENGINE_V2
        )
