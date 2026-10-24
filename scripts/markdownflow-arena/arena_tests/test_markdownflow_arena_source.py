# Assertions are pytest checks, never production runtime guards.
# ruff: noqa: S101

"""Verify private published snapshot selection and reproducible arena case inputs."""

from __future__ import annotations

import copy
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from flask import Flask
from flaskr.service.shifu.models import (
    AiCourseAuth,
    DraftShifu,
    LogPublishedStruct,
    PublishedOutlineItem,
    PublishedShifu,
)
from flaskr.service.user.models import AuthCredential, UserInfo
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from collections.abc import Iterator

# Synthetic fixture identifier; no test contains a real account phone.
TEST_OWNER_PHONE = "10000000000"

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from markdownflow_arena_lib import source  # noqa: E402
from markdownflow_arena_lib.state import ArenaError  # noqa: E402


@pytest.fixture
def snapshot_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Flask, Session]]:
    """Provide snapshot db for the isolated test fixture."""
    engine = create_engine("sqlite://")
    for model in (
        AiCourseAuth,
        DraftShifu,
        LogPublishedStruct,
        PublishedShifu,
        PublishedOutlineItem,
        AuthCredential,
        UserInfo,
    ):
        model.__table__.create(engine)
    with Session(engine) as session:
        monkeypatch.setattr(source, "_read_session", lambda _app: nullcontext(session))
        session.add(UserInfo(user_bid="owner", user_identify=TEST_OWNER_PHONE))
        session.commit()
        yield Flask(__name__), session
    engine.dispose()


def _course(
    session: Session, *, bid: str = "course", owner: str = "owner"
) -> tuple[PublishedShifu, PublishedOutlineItem, LogPublishedStruct]:
    course = PublishedShifu(
        shifu_bid=bid,
        title="Published course",
        llm_system_prompt="Course prompt",
        created_user_bid=owner,
    )
    draft = DraftShifu(
        shifu_bid=bid,
        title="Private draft",
        llm_system_prompt="Draft prompt must not escape",
        created_user_bid=owner,
    )
    session.add_all([course, draft])
    session.flush()
    parent = PublishedOutlineItem(
        shifu_bid=bid,
        outline_item_bid=f"{bid}-parent",
        content="",
        llm_system_prompt="Nearest published parent",
    )
    lesson = PublishedOutlineItem(
        shifu_bid=bid,
        outline_item_bid=f"{bid}-lesson",
        title="Published lesson",
        content="Create a PPT about vectors.\n\n---\n\nCreate an SVG diagram.",
    )
    visual = PublishedOutlineItem(
        shifu_bid=bid,
        outline_item_bid=f"{bid}-visual",
        title="Visual lesson",
        content="Create a PPT with an SVG diagram of a vector.",
    )
    session.add_all([parent, lesson, visual])
    session.flush()
    structure = {
        "type": "shifu",
        "id": course.id,
        "bid": bid,
        "children": [
            {
                "type": "outline",
                "id": parent.id,
                "bid": parent.outline_item_bid,
                "children": [
                    {
                        "type": "outline",
                        "id": lesson.id,
                        "bid": lesson.outline_item_bid,
                        "children": [],
                    },
                    {
                        "type": "outline",
                        "id": visual.id,
                        "bid": visual.outline_item_bid,
                        "children": [],
                    },
                ],
            }
        ],
    }
    published = LogPublishedStruct(
        shifu_bid=bid, struct_bid=f"struct-{bid}", struct=json.dumps(structure)
    )
    session.add(published)
    session.commit()
    return course, lesson, published


def test_snapshot_uses_published_row_ids_and_nearest_parent_without_writes(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify snapshot uses published row ids and nearest parent without writes."""
    app, session = snapshot_db
    course, lesson, published = _course(session)
    # A newer business-ID row that is absent from the published structure cannot
    # replace the precise row to which the publication points.
    session.add(
        PublishedOutlineItem(
            shifu_bid="course",
            outline_item_bid=lesson.outline_item_bid,
            content="Wrong independent latest row",
        )
    )
    session.commit()
    statements = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", capture)
    result = source.snapshot_courses(app, TEST_OWNER_PHONE)
    exported = next(
        item
        for item in result["courses"]
        if item["source"]["outline_bid"] == lesson.outline_item_bid
    )
    assert exported["document"] == lesson.content
    assert exported["document_prompt"] == "Nearest published parent"
    assert [item["kind"] for item in exported["prompt_chain"]] == [
        "course",
        "parent",
        "lesson",
    ]
    assert [item["prompt"] for item in exported["prompt_chain"]] == [
        "Course prompt",
        "Nearest published parent",
        "",
    ]
    assert exported["source"]["published_outline_id"] == lesson.id
    assert exported["source"]["published_shifu_id"] == course.id
    assert exported["source"]["published_struct_id"] == published.id
    assert all(
        statement.lstrip().upper().startswith("SELECT") for statement in statements
    )
    assert "Draft prompt" not in json.dumps(result)


@pytest.mark.parametrize(
    ("permission", "status", "allowed"),
    [
        ("view", 1, True),
        ("edit", 1, True),
        ("1", 1, True),
        ("2", 1, True),
        ("publish", 1, False),
        ("4", 1, False),
        ("view", 0, False),
        ("unknown", 1, False),
    ],
)
def test_view_permissions_never_widen_publish_only(
    snapshot_db: tuple[Flask, Session], permission: str, status: int, allowed: bool
) -> None:
    """Verify view permissions never widen publish only."""
    app, session = snapshot_db
    _course(session, owner="other-owner")
    session.add(
        AiCourseAuth(
            course_id="course",
            user_id="owner",
            auth_type=json.dumps([permission]),
            status=status,
        )
    )
    session.commit()
    snapshot = source.snapshot_courses(app, TEST_OWNER_PHONE)
    assert bool(snapshot["courses"]) is allowed


def test_broken_published_tree_never_falls_back_to_draft(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify broken published tree never falls back to draft."""
    app, session = snapshot_db
    _course(session)
    lesson = session.scalar(
        select(PublishedOutlineItem).where(
            PublishedOutlineItem.outline_item_bid == "course-lesson"
        )
    )
    lesson.deleted = 1
    session.commit()
    result = source.snapshot_courses(app, TEST_OWNER_PHONE)
    assert result["courses"] == []
    assert result["skipped"] == [
        {"shifu_bid": "course", "reason": "invalid_published_structure"}
    ]


def test_revalidate_rejects_revoked_permission_and_republished_snapshot(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify revalidate rejects revoked permission and republished snapshot."""
    app, session = snapshot_db
    _course(session, owner="another-owner")
    grant = AiCourseAuth(
        course_id="course", user_id="owner", auth_type='["view"]', status=1
    )
    session.add(grant)
    session.commit()
    cases = source.prepare_cases(
        source.snapshot_courses(app, TEST_OWNER_PHONE), 1, 7, {}
    )
    assert source.revalidate_sources(app, "owner", cases) == {cases[0]["case_id"]}
    grant.status = 0
    session.commit()
    assert source.revalidate_sources(app, "owner", cases) == set()
    grant.status = 1
    previous = session.scalar(select(LogPublishedStruct))
    session.add(
        LogPublishedStruct(
            shifu_bid="course", struct_bid="new-struct", struct=previous.struct
        )
    )
    session.commit()
    assert source.revalidate_sources(app, "owner", cases) == set()


@pytest.mark.parametrize("invalid_root", [None, [], ["outline"], 7, "course", True])
def test_non_object_published_tree_is_skipped_and_revocation_check_fails_closed(
    snapshot_db: tuple[Flask, Session], invalid_root: object
) -> None:
    """Verify non object published tree is skipped and revocation check fails closed."""
    app, session = snapshot_db
    _, _, published = _course(session)
    cases = source.prepare_cases(
        source.snapshot_courses(app, TEST_OWNER_PHONE), 1, 7, {}
    )
    published.struct = json.dumps(invalid_root)
    session.commit()

    result = source.snapshot_courses(app, TEST_OWNER_PHONE)
    assert result["courses"] == []
    assert result["skipped"] == [
        {"shifu_bid": "course", "reason": "invalid_published_structure"}
    ]
    assert source.revalidate_sources(app, "owner", cases) == set()


def test_prepare_cases_is_reproducible_and_freezes_variables(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify prepare cases is reproducible and freezes variables."""
    app, session = snapshot_db
    _course(session)
    snapshot = source.snapshot_courses(app, TEST_OWNER_PHONE)
    variables = {"sys_user_background": "Synthetic evaluator", "language": "zh-CN"}
    first = source.prepare_cases(snapshot, 2, 123, variables)
    second = source.prepare_cases(snapshot, 2, 123, variables)
    assert first == second
    assert {case["category"] for case in first} == {"slides"}
    variables["sys_user_background"] = "Changed later"
    assert first[0]["variables"]["sys_user_background"] == "Synthetic evaluator"
    altered = copy.deepcopy(first[0])
    altered["variables"]["language"] = "en-US"
    assert source.case_input_hash(altered) != first[0]["input_hash"]
    assert all(case["context"] == [] and case["user_input"] is None for case in first)


def test_prepare_skips_missing_variables_preserved_and_interaction_blocks() -> None:
    """Verify prepare skips missing variables preserved and interaction blocks."""
    snapshot = {
        "owner_user_bid": "owner",
        "courses": [
            {
                "source": {},
                "document": "Explain {{missing}}.\n\n?[A|B]\n\n!===\nFixed text\n!===",
                "document_prompt": "",
                "use_learner_language": False,
            }
        ],
    }
    with pytest.raises(ArenaError, match="Only 0 eligible"):
        source.prepare_cases(snapshot, 1, 0, {})
    assert {item["reason"] for item in snapshot["skipped"]} == {
        "missing_variables",
        "prior_context_required",
        "preserved_content",
    }


def test_prepare_rejects_content_after_preserved_context() -> None:
    """Verify prepare rejects content after preserved context."""
    snapshot = {
        "owner_user_bid": "owner",
        "courses": [
            {
                "source": {"shifu_bid": "course", "outline_bid": "lesson"},
                "document": (
                    "!===\nThe fixed example has a value of 42.\n!==="
                    "\n\n---\n\nExplain the example above."
                ),
                "document_prompt": "",
                "use_learner_language": False,
            }
        ],
    }
    with pytest.raises(ArenaError, match="Only 0 eligible"):
        source.prepare_cases(snapshot, 1, 0, {})
    assert [(item["block_index"], item["reason"]) for item in snapshot["skipped"]] == [
        (0, "preserved_content"),
        (1, "prior_context_required"),
    ]


@pytest.mark.parametrize(
    "interaction",
    [
        "?[{{topic}} | Other]",
        "?[...Explain {{topic}}]",
        "?[%{{answer}} {{topic}} | Other]",
    ],
)
def test_prepare_checks_next_interaction_input_without_requiring_assignment_target(
    interaction: str,
) -> None:
    """Verify prepare checks next interaction input without requiring assignment target."""
    snapshot = {
        "owner_user_bid": "owner",
        "courses": [
            {
                "source": {"shifu_bid": "course", "outline_bid": "lesson"},
                "document": f"Create a PPT about the topic.\n\n{interaction}",
                "document_prompt": "",
                "use_learner_language": False,
            }
        ],
    }
    with pytest.raises(ArenaError, match="Only 0 eligible"):
        source.prepare_cases(snapshot, 1, 0, {})
    missing = next(
        item for item in snapshot["skipped"] if item["reason"] == "missing_variables"
    )
    assert missing["block_index"] == 0
    assert missing["missing_variables"] == ["topic"]
    case = source.prepare_cases(snapshot, 1, 0, {"topic": "Vectors"})[0]
    assert case["block_index"] == 0
    assert "answer" not in case["variables"]
    assert case["context"] == []


def test_sampling_covers_distinct_courses_before_reusing_course(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify sampling covers distinct courses before reusing course."""
    app, session = snapshot_db
    _course(session, bid="one")
    _course(session, bid="two")
    snapshot = source.snapshot_courses(app, TEST_OWNER_PHONE)
    cases = source.prepare_cases(snapshot, 2, 12, {})
    assert {case["source"]["shifu_bid"] for case in cases} == {"one", "two"}
    assert {case["category"] for case in cases} == {"slides"}
    assert all(case["block_index"] == 0 for case in cases)
    assert any(
        item["reason"] == "prior_context_required" for item in snapshot["skipped"]
    )
    original_skipped = copy.deepcopy(snapshot["skipped"])
    assert source.prepare_cases(snapshot, 2, 12, {}) == cases
    assert snapshot["skipped"] == original_skipped


@pytest.mark.parametrize("level", ["course", "parent", "lesson"])
def test_slide_intent_uses_effective_inherited_published_prompt(
    snapshot_db: tuple[Flask, Session], level: str
) -> None:
    """Verify slide intent uses effective inherited published prompt."""
    app, session = snapshot_db
    course, lesson, _published = _course(session)
    parent = session.scalar(
        select(PublishedOutlineItem).where(
            PublishedOutlineItem.outline_item_bid == "course-parent"
        )
    )
    course.llm_system_prompt = parent.llm_system_prompt = lesson.llm_system_prompt = ""
    lesson.content = "Introduce vectors."
    {"course": course, "parent": parent, "lesson": lesson}[
        level
    ].llm_system_prompt = "Create PPT slides to teach the topic."
    session.commit()
    cases = source.prepare_cases(
        source.snapshot_courses(app, TEST_OWNER_PHONE), 2, 18, {}
    )
    case = next(
        item
        for item in cases
        if item["source"]["outline_bid"] == lesson.outline_item_bid
    )
    assert case["category"] == "slides"
    assert case["document_prompt"] == "Create PPT slides to teach the topic."


@pytest.mark.parametrize(
    "content",
    [
        "Draw a diagram.",
        "Render <html>hello</html>.",
        "Explain a formula.",
        "Explain what PPT means.",
        "Only create slides when explicitly instructed.",
    ],
)
def test_non_slide_generation_is_skipped(content: str) -> None:
    """Verify non slide generation is skipped."""
    snapshot = {
        "owner_user_bid": "owner",
        "courses": [
            {
                "source": {},
                "document": content,
                "document_prompt": "",
                "use_learner_language": False,
            }
        ],
    }
    with pytest.raises(ArenaError, match="Only 0 eligible"):
        source.prepare_cases(snapshot, 1, 0, {})
    assert snapshot["skipped"][0]["reason"] == "not_slide_generation"


def test_slide_only_sampling_preserves_course_coverage() -> None:
    """Verify slide only sampling preserves course coverage."""
    snapshot = {
        "owner_user_bid": "owner",
        "courses": [
            {
                "source": {
                    "shifu_bid": f"course-{course}",
                    "outline_bid": f"lesson-{course}-{lesson}",
                },
                "document": "Create PPT slides about the topic.",
                "document_prompt": "",
                "use_learner_language": False,
            }
            for course in range(12)
            for lesson in range(3)
        ],
    }
    cases = source.prepare_cases(snapshot, 12, 902, {})
    assert len({case["source"]["shifu_bid"] for case in cases}) == 12
    assert {case["category"] for case in cases} == {"slides"}
    assert cases == source.prepare_cases(snapshot, 12, 902, {})


def test_missing_owner_fails_before_source_queries(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify missing owner fails before source queries."""
    app, session = snapshot_db
    owner = session.scalar(select(UserInfo))
    owner.deleted = 1
    session.commit()
    with pytest.raises(ArenaError, match="active account"):
        source.snapshot_courses(app, TEST_OWNER_PHONE)


def test_duplicate_phone_uses_login_canonical_account_without_aggregating_access(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify duplicate phone uses login canonical account without aggregating access."""
    app, session = snapshot_db
    session.add(UserInfo(user_bid="another", user_identify=TEST_OWNER_PHONE))
    session.add(
        AuthCredential(
            user_bid="another", provider_name="phone", identifier=TEST_OWNER_PHONE
        )
    )
    _course(session, bid="canonical-course")
    _course(session, bid="legacy-course", owner="another")
    session.commit()
    snapshot = source.snapshot_courses(app, TEST_OWNER_PHONE)
    assert snapshot["owner_user_bid"] == "owner"
    assert snapshot["owner_resolution_method"] == "phone_login_canonical"
    assert {item["source"]["shifu_bid"] for item in snapshot["courses"]} == {
        "canonical-course"
    }


@pytest.mark.parametrize("canonical_match", [True, False])
def test_owner_resolution_matches_existing_phone_login_repository(
    canonical_match: bool,
) -> None:
    """Verify owner resolution matches existing phone login repository."""
    from flaskr.dao import db
    from flaskr.service.user.repository import load_user_aggregate_by_identifier

    app = Flask("arena-phone-login-parity")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db.init_app(app)
    with app.app_context():
        UserInfo.__table__.create(db.engine)
        AuthCredential.__table__.create(db.engine)
        db.session.add_all(
            [
                UserInfo(
                    user_bid="first-canonical",
                    user_identify=TEST_OWNER_PHONE if canonical_match else "one",
                ),
                UserInfo(
                    user_bid="first-credential",
                    user_identify=TEST_OWNER_PHONE if canonical_match else "two",
                ),
                AuthCredential(
                    user_bid="first-credential",
                    provider_name="phone",
                    identifier=TEST_OWNER_PHONE,
                ),
                AuthCredential(
                    user_bid="first-canonical",
                    provider_name="phone",
                    identifier=TEST_OWNER_PHONE,
                ),
            ]
        )
        db.session.commit()
        login_account = load_user_aggregate_by_identifier(
            TEST_OWNER_PHONE, providers=["phone"]
        )
        assert login_account is not None
        assert source.resolve_owner_user_bid(app, TEST_OWNER_PHONE) == (
            login_account.user_bid
        )
        assert source.resolve_owner_user_bid(app, f"+86{TEST_OWNER_PHONE}") == (
            login_account.user_bid
        )


@pytest.mark.parametrize("deleted_user", [True, False])
def test_owner_resolution_never_skips_orphaned_first_phone_credential(
    snapshot_db: tuple[Flask, Session], deleted_user: bool
) -> None:
    """Verify owner resolution never skips orphaned first phone credential."""
    app, session = snapshot_db
    session.scalar(select(UserInfo)).user_identify = "unrelated"
    if deleted_user:
        session.add(UserInfo(user_bid="invalid", user_identify="gone", deleted=1))
    session.add_all(
        [
            AuthCredential(
                user_bid="invalid", provider_name="phone", identifier=TEST_OWNER_PHONE
            ),
            AuthCredential(
                user_bid="owner", provider_name="phone", identifier=TEST_OWNER_PHONE
            ),
        ]
    )
    session.commit()
    with pytest.raises(ArenaError, match="active account"):
        source.resolve_owner_user_bid(app, TEST_OWNER_PHONE)


@pytest.mark.parametrize(
    ("provider", "identifier"),
    [("sms", TEST_OWNER_PHONE), ("phone", f"86{TEST_OWNER_PHONE}")],
)
def test_owner_resolution_never_expands_provider_or_phone_spellings(
    snapshot_db: tuple[Flask, Session], provider: str, identifier: str
) -> None:
    """Verify owner resolution never expands provider or phone spellings."""
    app, session = snapshot_db
    session.scalar(select(UserInfo)).user_identify = "unrelated"
    session.add(
        AuthCredential(user_bid="owner", provider_name=provider, identifier=identifier)
    )
    session.commit()
    with pytest.raises(ArenaError, match="active account"):
        source.resolve_owner_user_bid(app, TEST_OWNER_PHONE)


def test_current_draft_ownership_overrides_previous_published_owner(
    snapshot_db: tuple[Flask, Session],
) -> None:
    """Verify current draft ownership overrides previous published owner."""
    app, session = snapshot_db
    _course(session)
    draft = session.scalar(select(DraftShifu))
    draft.created_user_bid = "new-owner"
    session.commit()
    assert source.snapshot_courses(app, TEST_OWNER_PHONE)["courses"] == []


def test_read_session_never_flushes_or_commits_and_isolates_pending_changes() -> None:
    """Verify read session never flushes or commits and isolates pending changes."""
    from flaskr.dao import db

    app = Flask("arena-source-read-session")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db.init_app(app)
    with app.app_context():
        UserInfo.__table__.create(db.engine)
        with db.engine.begin() as connection:
            connection.execute(
                UserInfo.__table__.insert().values(
                    user_bid="owner",
                    user_identify=TEST_OWNER_PHONE,
                    nickname="Original",
                )
            )
        statements = []

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        with source._read_session(app) as session:
            owner = session.scalar(select(UserInfo))
            owner.nickname = "Must never be stored"
            session.scalar(select(UserInfo.id))
        with source._read_session(app) as session:
            assert session.scalar(select(UserInfo.nickname)) == "Original"
        assert statements
        assert all(
            statement.lstrip().upper().startswith("SELECT") for statement in statements
        )


@pytest.mark.parametrize(
    "content",
    [
        "Do not create slide 1: introduction",
        "不要创建幻灯片 1：介绍",
        "Only create slide 1: when instructed",
        "If requested, create slide 1: introduction",
        "如果需要，生成幻灯片 1：介绍",
        "Create slides only if requested.",
        "仅在要求时生成幻灯片 1：介绍",
        "Create slides only upon request.",
        "Create slides, if requested.",
    ],
)
def test_negated_or_conditional_numbered_slides_are_skipped(content: str) -> None:
    """Reject numbered slide commands whose generation is forbidden or conditional."""
    test_non_slide_generation_is_skipped(content)


@pytest.mark.parametrize(
    "content",
    [
        "Create slides, but do not overcrowd them",
        "生成幻灯片，不要堆叠文字",
        "Create slides but do not overcrowd them",
        "Create only two slides with concise text",
        "生成幻灯片但不要堆叠文字",
        "Slide 1: introduction",
        "幻灯片 1：介绍",
        "不要堆叠文字，生成幻灯片",
    ],
)
def test_affirmative_slides_keep_negative_layout_constraints(content: str) -> None:
    """Accept real slide tasks without discarding their layout restrictions."""
    for document, inherited in [(content, ""), ("Explain the topic", content)]:
        snapshot = {
            "owner_user_bid": "owner",
            "courses": [
                {"source": {}, "document": document, "document_prompt": inherited}
            ],
        }
        cases = source.prepare_cases(snapshot, 1, 0, {})
        assert len(cases) == 1
        assert cases[0]["category"] == "slides"
