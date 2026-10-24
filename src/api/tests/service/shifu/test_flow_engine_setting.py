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
from flaskr.service.shifu.models import (
    DraftOutlineItem,
    DraftShifu,
    PublishedShifu,
)

SHIFU = "course-under-test"


@pytest.fixture(autouse=True)
def _clean(app: object):  # noqa: ANN202 - pytest fixture
    with app.app_context():
        DraftShifu.query.filter_by(shifu_bid=SHIFU).delete()
        PublishedShifu.query.filter_by(shifu_bid=SHIFU).delete()
        DraftOutlineItem.query.filter_by(shifu_bid=SHIFU).delete()
        db.session.commit()
        yield
        DraftShifu.query.filter_by(shifu_bid=SHIFU).delete()
        PublishedShifu.query.filter_by(shifu_bid=SHIFU).delete()
        DraftOutlineItem.query.filter_by(shifu_bid=SHIFU).delete()
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


def test_editing_a_draft_keeps_the_runtime(app: object) -> None:
    """Ordinary edits clone the draft into a new version, and the clone keeps the runtime.

    A clone that dropped the setting would quietly send the course back to 1.0 on its next publish.
    """
    with app.app_context():
        draft = DraftShifu(shifu_bid=SHIFU, title="before", flow_engine=FLOW_ENGINE_V2)
        db.session.add(draft)
        db.session.commit()

        clone = draft.clone()
        clone.title = "after"
        db.session.add(clone)
        db.session.commit()

        assert clone.flow_engine == FLOW_ENGINE_V2


def test_a_runtime_only_change_counts_as_a_change(app: object) -> None:
    """Switching only the runtime has to count as a change.

    `eq` decides whether a new version is written at all, so without the field that edit would be
    treated as no change and silently dropped.
    """
    with app.app_context():
        a = DraftShifu(shifu_bid=SHIFU, title="t", flow_engine=FLOW_ENGINE_V1)
        b = a.clone()
        b.flow_engine = FLOW_ENGINE_V2

        assert a.eq(b) is False


def _import_payload(**shifu_overrides: object) -> object:
    """Build a minimal export file, in the shape `import_shifu` expects to receive."""
    import io
    import json

    from werkzeug.datastructures import FileStorage

    payload = {
        "shifu": {
            "title": "Imported",
            "description": "d",
            "keywords": "k",
            **shifu_overrides,
        },
        "outline_items": [],
    }
    return FileStorage(
        stream=io.BytesIO(json.dumps(payload).encode()), filename="course.json"
    )


def _imported_runtime(app: object, payload: object) -> int:
    from flaskr.service.shifu.shifu_import_export_funcs import import_shifu

    bid = import_shifu(app, None, payload, "user-1")
    with app.app_context():
        created = (
            DraftShifu.query.filter_by(shifu_bid=bid)
            .order_by(DraftShifu.id.desc())
            .first()
        )
        assert created is not None
        runtime = created.flow_engine
        DraftShifu.query.filter_by(shifu_bid=bid).delete()
        db.session.commit()
    return runtime


def test_an_imported_course_arrives_on_the_runtime_it_was_exported_with(
    app: object,
) -> None:
    """Importing is where the setting is reconstructed, and where dropping it would be silent."""
    assert _imported_runtime(app, _import_payload(flow_engine=FLOW_ENGINE_V2)) == (
        FLOW_ENGINE_V2
    )


def test_a_file_written_before_this_setting_imports_as_the_old_runtime(
    app: object,
) -> None:
    """Old export files have no key at all, and describe courses that ran on 1.0."""
    assert _imported_runtime(app, _import_payload()) == FLOW_ENGINE_V1
