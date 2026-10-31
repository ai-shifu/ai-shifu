"""Exercise durable installation claims, ownership and legacy upgrade boundaries."""

from __future__ import annotations

import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.common.models import AppError
from flaskr.service.user import installation, post_auth
from flaskr.service.user.consts import USER_STATE_REGISTERED
from flaskr.service.user.installation_models import InstallationState, LocalAdminAccount
from flaskr.service.user.models import AuthCredential, UserInfo
from flaskr.service.user.phone_flow import init_first_course
from flaskr.service.user.repository import load_user_aggregate
from flaskr.util.datetime import now_utc
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError


@pytest.fixture
def installation_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'installation.db'}",
        SQLALCHEMY_ENGINE_OPTIONS={
            "connect_args": {"timeout": 10, "check_same_thread": False}
        },
        SECRET_KEY="installation-test-secret",
    )
    db.init_app(app)
    from flaskr.service.user import utils

    monkeypatch.setattr(utils, "ensure_demo_course_permissions", Mock())
    monkeypatch.setattr(post_auth, "run_post_auth_extensions", Mock())
    from flaskr.service.user.installation_cli import register_installation_commands

    @app.cli.group("console")
    def console() -> None:
        """Expose the installation test console."""

    register_installation_commands(console, app)
    with app.app_context():
        db.create_all(bind_key=None)
        db.session.add(InstallationState(id=1, mode="managed"))
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all(bind_key=None)


def _initialize(app: Flask, token: str, **changes: str) -> str:
    values = {
        "setup_token": token,
        "identifier": "owner@example.com",
        "password": "OwnerPassword123",
        "request_origin": "http://localhost:8080",
    }
    values.update(changes)
    return installation.initialize_admin(app, **values)


def test_setup_atomically_creates_owner_without_external_provider(
    installation_app: Flask,
) -> None:
    app = installation_app
    assert installation.get_installation_status(app) == {
        "setup_required": True,
        "local_admin_login_enabled": False,
    }
    token = installation.issue_setup_token(app)
    user_bid = _initialize(app, token)
    with app.app_context():
        state = db.session.get(InstallationState, 1)
        account = LocalAdminAccount.query.one()
        user = UserInfo.query.filter_by(user_bid=user_bid).one()
        assert account.user_bid == user_bid
        assert user.is_operator == user.is_creator == 1
        aggregate = load_user_aggregate(user_bid)
        assert aggregate.email == "owner@example.com"
        assert not aggregate.mobile
        assert aggregate.has_password is True
        assert aggregate.has_local_password is False
        assert state.initialized_user_bid == user_bid
        assert state.initialized_at is not None
        assert state.token_digest == ""
        assert state.token_expires_at is None
        assert (
            AuthCredential.query.filter(
                AuthCredential.provider_name.in_(["email", "phone"])
            ).count()
            == 0
        )
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": True,
    }
    context = post_auth.run_post_auth_extensions.call_args.args[1]
    assert context.creator_granted_now
    assert context.created_new_user
    assert context.user_id == user_bid
    with pytest.raises(AppError):
        _initialize(app, token, identifier="second@example.com")
    with pytest.raises(AppError):
        installation.issue_setup_token(app)


def test_claim_is_hashed_rotated_and_origin_bound(installation_app: Flask) -> None:
    app = installation_app
    first = installation.issue_setup_token(app)
    second = installation.issue_setup_token(app)
    assert first != second
    with app.app_context():
        state = db.session.get(InstallationState, 1)
        assert second not in state.token_digest
        assert len(state.token_digest) == 64
    for token, origin in (
        (first, "http://localhost:8080"),
        (second, "https://other.example.com"),
        ("x" * 43, "http://localhost:8080"),
    ):
        with pytest.raises(AppError):
            _initialize(app, token, request_origin=origin)
    _initialize(app, second)


def test_expired_claim_leaves_setup_available_but_does_not_create_user(
    installation_app: Flask,
) -> None:
    app = installation_app
    token = installation.issue_setup_token(app)
    with app.app_context(), unit_of_work():
        db.session.get(InstallationState, 1).token_expires_at = now_utc() - timedelta(
            seconds=1
        )
    with pytest.raises(AppError):
        _initialize(app, token)
    with app.app_context():
        assert LocalAdminAccount.query.count() == 0
    assert installation.get_installation_status(app)["setup_required"]


def test_mid_flow_failure_rolls_back_credentials_roles_claim_and_completion(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = installation_app
    token = installation.issue_setup_token(app)
    original = installation.assign_configured_demo_ownership
    failure = Mock(side_effect=RuntimeError("simulated ownership failure"))
    monkeypatch.setattr(installation, "assign_configured_demo_ownership", failure)
    with pytest.raises(RuntimeError, match="ownership failure"):
        _initialize(app, token)
    with app.app_context():
        assert UserInfo.query.count() == 0
        assert LocalAdminAccount.query.count() == 0
        assert AuthCredential.query.count() == 0
        assert db.session.get(InstallationState, 1).initialized_at is None
    post_auth.run_post_auth_extensions.assert_not_called()
    monkeypatch.setattr(installation, "assign_configured_demo_ownership", original)
    _initialize(app, token)


def test_two_concurrent_setup_requests_have_one_committed_winner(
    installation_app: Flask,
) -> None:
    app = installation_app
    token = installation.issue_setup_token(app)
    start = threading.Barrier(2)

    def attempt(identifier: str) -> str:
        start.wait(timeout=5)
        try:
            return _initialize(app, token, identifier=identifier)
        except AppError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt, identifier)
            for identifier in ("one@example.com", "two@example.com")
        ]
        outcomes = [future.result(timeout=15) for future in futures]
    assert outcomes.count("rejected") == 1
    with app.app_context():
        assert LocalAdminAccount.query.count() == 1
        assert UserInfo.query.count() == 1
        assert db.session.get(InstallationState, 1).initialized_at is not None


def test_completion_survives_user_deletion_and_new_application_context(
    installation_app: Flask,
) -> None:
    app = installation_app
    user_bid = _initialize(app, installation.issue_setup_token(app))
    with app.app_context(), unit_of_work():
        UserInfo.query.filter_by(user_bid=user_bid).delete()
        db.session.expire_all()
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": False,
    }
    with pytest.raises(AppError):
        installation.issue_setup_token(app)


@pytest.mark.parametrize(
    ("mode", "completed"), [("managed", False), ("managed", True), ("legacy", True)]
)
def test_public_first_user_promotion_is_closed(
    installation_app: Flask, mode: str, completed: bool
) -> None:
    app = installation_app
    with app.app_context(), unit_of_work():
        state = db.session.get(InstallationState, 1)
        state.mode = mode
        state.initialized_at = now_utc() if completed else None
        user = UserInfo(
            user_bid="public-account",
            user_identify="owner@example.com",
            state=USER_STATE_REGISTERED,
            deleted=0,
        )
        db.session.add(user)
        db.session.flush()
        assert not installation.allows_legacy_first_user_bootstrap(app)
        assert init_first_course(app, "public-account") is False
        assert user.is_operator == 0


def test_missing_installation_state_fails_closed(installation_app: Flask) -> None:
    app = installation_app
    with app.app_context(), unit_of_work():
        InstallationState.query.delete()
        user = UserInfo(
            user_bid="public-account",
            user_identify="owner@example.com",
            state=USER_STATE_REGISTERED,
            deleted=0,
        )
        db.session.add(user)
        db.session.flush()
        assert not installation.allows_legacy_first_user_bootstrap(app)
        assert init_first_course(app, user.user_bid) is False
        assert user.is_operator == 0
    assert not installation.get_installation_status(app)["setup_required"]
    with pytest.raises(AppError):
        installation.issue_setup_token(app)


def test_explicit_legacy_bootstrap_is_sealed_before_future_user_deletion(
    installation_app: Flask,
) -> None:
    app = installation_app
    with app.app_context(), unit_of_work():
        state = db.session.get(InstallationState, 1)
        state.mode = "legacy"
        user = UserInfo(
            user_bid="historic-owner",
            user_identify="owner@example.com",
            state=USER_STATE_REGISTERED,
            deleted=0,
        )
        db.session.add(user)
        db.session.flush()
        assert init_first_course(app, user.user_bid)
        assert user.is_operator == user.is_creator == 1
        assert db.session.get(InstallationState, 1).initialized_at is not None
        assert not installation.allows_legacy_first_user_bootstrap(app)
        UserInfo.query.delete()
    assert not installation.allows_legacy_first_user_bootstrap(app)


def test_managed_owner_receives_published_and_draft_demo_ownership(
    installation_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
    from flaskr.service.user import utils

    app = installation_app
    monkeypatch.setattr(utils, "load_existing_demo_shifu_ids", lambda: {"bundled-demo"})
    with app.app_context(), unit_of_work():
        db.session.add(PublishedShifu(shifu_bid="bundled-demo", title="Demo"))
        db.session.add(DraftShifu(shifu_bid="bundled-demo", title="Demo draft"))
    user_bid = _initialize(app, installation.issue_setup_token(app))
    with app.app_context():
        assert PublishedShifu.query.one().created_user_bid == user_bid
        assert DraftShifu.query.one().created_user_bid == user_bid


def test_managed_setup_never_claims_a_sole_ordinary_course(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
    from flaskr.service.user import utils

    monkeypatch.setattr(utils, "load_existing_demo_shifu_ids", set)
    app = installation_app
    with app.app_context(), unit_of_work():
        db.session.add(
            PublishedShifu(
                shifu_bid="ordinary-course",
                title="Teacher course",
                created_user_bid="existing-teacher",
            )
        )
        db.session.add(
            DraftShifu(
                shifu_bid="ordinary-course",
                title="Teacher draft",
                created_user_bid="existing-teacher",
            )
        )
    _initialize(app, installation.issue_setup_token(app))
    with app.app_context():
        assert PublishedShifu.query.one().created_user_bid == "existing-teacher"
        assert DraftShifu.query.one().created_user_bid == "existing-teacher"


def test_managed_setup_claims_configured_demos_only_among_multiple_courses(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu
    from flaskr.service.user import utils

    demo_ids = {"chinese-demo", "english-demo"}
    monkeypatch.setattr(utils, "load_existing_demo_shifu_ids", lambda: demo_ids)
    app = installation_app
    with app.app_context(), unit_of_work():
        for bid in (*sorted(demo_ids), "ordinary-course"):
            for model in (PublishedShifu, DraftShifu):
                db.session.add(
                    model(
                        shifu_bid=bid,
                        title="Course",
                        created_user_bid="existing-teacher",
                    )
                )
    user_bid = _initialize(app, installation.issue_setup_token(app))
    with app.app_context():
        for model in (PublishedShifu, DraftShifu):
            for course in model.query.all():
                expected = (
                    user_bid if course.shifu_bid in demo_ids else "existing-teacher"
                )
                assert course.created_user_bid == expected


def test_post_commit_creator_extension_failure_does_not_reopen_installation(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        post_auth,
        "run_post_auth_extensions",
        Mock(side_effect=RuntimeError("simulated extension failure")),
    )
    app = installation_app
    _initialize(app, installation.issue_setup_token(app))
    assert installation.get_installation_status(app) == {
        "setup_required": False,
        "local_admin_login_enabled": True,
    }


def test_trusted_console_can_seed_closed_legacy_without_reopening_setup(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    assign = Mock()
    monkeypatch.setattr(installation, "assign_configured_demo_ownership", assign)
    app = installation_app
    with app.app_context(), unit_of_work():
        state = db.session.get(InstallationState, 1)
        state.mode = "legacy"
        state.initialized_at = now_utc()
    installation.create_admin_from_console(
        app, identifier="legacy@example.com", password="Password123"
    )
    assign.assert_not_called()
    assert not installation.get_installation_status(app)["setup_required"]
    with pytest.raises(AppError):
        installation.create_admin_from_console(
            app, identifier="another@example.com", password="Password123"
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://[::1]:8080",
        "https://site.example.com",
    ],
)
def test_setup_origin_accepts_safe_transports(origin: str) -> None:
    assert installation.normalize_setup_origin(origin) == origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://site.example.com",
        "http://192.168.1.1",
        "https://user:secret@example.com",
        "https://example.com/?token=secret",
        "",
        "file:///setup",
    ],
)
def test_setup_origin_rejects_unsafe_or_secret_bearing_urls(origin: str) -> None:
    with pytest.raises(AppError):
        installation.normalize_setup_origin(origin)


def test_provenance_capture_precedes_schema_writes_and_is_immutable(
    tmp_path: Path,
) -> None:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_path / 'fresh.db'}"
    db.init_app(app)
    assert installation.capture_installation_database_provenance(app)
    with app.app_context(), db.engine.begin() as connection:
        connection.execute(text("CREATE TABLE plugin_marker (id INTEGER)"))
    assert installation.capture_installation_database_provenance(app)


def test_provenance_database_failure_is_closed_and_not_retried(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = installation_app
    failure = Mock(side_effect=SQLAlchemyError("unavailable"))
    monkeypatch.setattr(installation, "inspect", failure)
    assert not installation.capture_installation_database_provenance(app)
    assert not installation.capture_installation_database_provenance(app)
    failure.assert_called_once()


@pytest.mark.parametrize("fresh", [False, True])
def test_prepare_wrapper_forwards_only_captured_fresh_provenance(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch, fresh: bool
) -> None:
    import flask_migrate

    app = installation_app
    app.extensions[installation.INSTALLATION_PROVENANCE_EXTENSION] = fresh
    upgrade = Mock()
    monkeypatch.setattr(flask_migrate, "upgrade", upgrade)
    installation.prepare_installation_database(app)
    assert upgrade.call_args.kwargs["x_arg"] == (
        [installation.FRESH_INSTALLATION_MIGRATION_ARGUMENT] if fresh else None
    )


@pytest.mark.parametrize("fresh", [False, True])
def test_migration_seeds_managed_pending_only_with_trusted_fresh_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh: bool
) -> None:
    path = (
        Path(__file__).parents[3]
        / "migrations/versions/b8e4a1d3c9f0_add_installation_bootstrap_state.py"
    )
    spec = importlib.util.spec_from_file_location("installation_revision", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        monkeypatch.setattr(
            module, "op", Operations(MigrationContext.configure(connection))
        )
        monkeypatch.setattr(
            module.context,
            "get_x_argument",
            lambda **_kwargs: {"ai_shifu_fresh_installation": "true"} if fresh else {},
        )
        module.upgrade()
        row = connection.execute(
            text("SELECT mode, initialized_at FROM user_installation_state")
        ).one()
        assert row.mode == ("managed" if fresh else "legacy")
        assert (row.initialized_at is None) is fresh
        assert "user_local_admin_accounts" in inspect(connection).get_table_names()
        module.downgrade()
        assert "user_installation_state" not in inspect(connection).get_table_names()
    engine.dispose()


def test_console_setup_code_is_explicit_output_not_application_log(
    installation_app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    app = installation_app
    result = app.test_cli_runner().invoke(args=["console", "setup-code"])
    assert result.exit_code == 0, result.output
    token = result.output.splitlines()[1]
    assert len(token) == 43
    assert token not in caplog.text
    _initialize(app, token)


def test_console_create_admin_prompts_without_echoing_password(
    installation_app: Flask,
) -> None:
    app = installation_app
    result = app.test_cli_runner().invoke(
        args=["console", "create-admin"],
        input="console@example.com\nHiddenPassword123\nHiddenPassword123\n",
    )
    assert result.exit_code == 0, result.output
    assert "HiddenPassword123" not in result.output
    assert "Local administrator created" in result.output
    assert installation.get_installation_status(app)["local_admin_login_enabled"]


def test_console_reset_uses_hidden_confirmation_and_shared_recovery_helper(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.user import local_accounts

    reset = Mock()
    monkeypatch.setattr(local_accounts, "reset_local_admin_password", reset)
    result = installation_app.test_cli_runner().invoke(
        args=["console", "reset-admin-password", "--identifier", "console@example.com"],
        input="NewPassword123\nNewPassword123\n",
    )
    assert result.exit_code == 0, result.output
    assert "NewPassword123" not in result.output
    reset.assert_called_once_with(
        installation_app,
        identifier="console@example.com",
        new_password="NewPassword123",
    )


def test_console_prepare_delegates_provenance_aware_migration(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare = Mock()
    monkeypatch.setattr(installation, "prepare_installation_database", prepare)
    result = installation_app.test_cli_runner().invoke(
        args=["console", "prepare-installation"]
    )
    assert result.exit_code == 0, result.output
    prepare.assert_called_once_with(installation_app)


def test_console_development_repair_keeps_fresh_snapshot_in_same_process(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import repair_dev_migration_state

    app = installation_app
    app.extensions[installation.INSTALLATION_PROVENANCE_EXTENSION] = True
    calls = []

    def repair() -> int:
        assert installation.capture_installation_database_provenance(app)
        calls.append("repair")
        return 0

    def prepare(prepared_app: Flask) -> None:
        assert prepared_app is app
        assert installation.capture_installation_database_provenance(app)
        calls.append("prepare")

    monkeypatch.setattr(repair_dev_migration_state, "main", repair)
    monkeypatch.setattr(installation, "prepare_installation_database", prepare)
    result = app.test_cli_runner().invoke(
        args=["console", "prepare-installation", "--repair-development"]
    )
    assert result.exit_code == 0, result.output
    assert calls == ["repair", "prepare"]


def test_console_development_repair_failure_prevents_migration(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import repair_dev_migration_state

    prepare = Mock()
    monkeypatch.setattr(repair_dev_migration_state, "main", lambda: 1)
    monkeypatch.setattr(installation, "prepare_installation_database", prepare)
    result = installation_app.test_cli_runner().invoke(
        args=["console", "prepare-installation", "--repair-development"]
    )
    assert result.exit_code == 1
    prepare.assert_not_called()


@pytest.mark.parametrize("deleted", [0, 1])
def test_downgrade_refuses_local_bindings_before_dropping_any_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deleted: int
) -> None:
    path = (
        Path(__file__).parents[3]
        / "migrations/versions/b8e4a1d3c9f0_add_installation_bootstrap_state.py"
    )
    spec = importlib.util.spec_from_file_location(
        "installation_downgrade_revision", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{tmp_path / 'downgrade.db'}")
    with engine.begin() as connection:
        monkeypatch.setattr(
            module, "op", Operations(MigrationContext.configure(connection))
        )
        monkeypatch.setattr(module.context, "get_x_argument", lambda **_kwargs: {})
        module.upgrade()
        connection.execute(
            text(
                "INSERT INTO user_local_admin_accounts (username,user_bid,credential_bid,deleted,created_at,updated_at) VALUES (:identifier,:user_bid,:credential_bid,:deleted,:created_at,:updated_at)"
            ),
            {
                "identifier": "owner",
                "user_bid": "owner-user",
                "credential_bid": "owner-credential",
                "deleted": deleted,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            },
        )
        with pytest.raises(RuntimeError, match="local administrator bindings exist"):
            module.downgrade()
        assert "user_local_admin_accounts" in inspect(connection).get_table_names()
        assert "user_installation_state" in inspect(connection).get_table_names()
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM user_local_admin_accounts")
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_hidden_username_recovery_alias_does_not_create_new_username_accounts(
    installation_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    from flaskr.service.user import local_accounts

    reset = Mock()
    monkeypatch.setattr(local_accounts, "reset_local_admin_password", reset)
    result = installation_app.test_cli_runner().invoke(
        args=["console", "reset-admin-password", "--username", "old_owner"],
        input="NewPassword123\nNewPassword123\n",
    )
    assert result.exit_code == 0, result.output
    reset.assert_called_once_with(
        installation_app, identifier="old_owner", new_password="NewPassword123"
    )
    help_result = installation_app.test_cli_runner().invoke(
        args=["console", "reset-admin-password", "--help"]
    )
    assert "--identifier" in help_result.output
    assert "--username" not in help_result.output
    create_result = installation_app.test_cli_runner().invoke(
        args=["console", "create-admin", "--username", "old_owner"]
    )
    assert create_result.exit_code != 0
