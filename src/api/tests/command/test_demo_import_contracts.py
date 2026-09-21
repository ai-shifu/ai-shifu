"""Protect demo import idempotency, publication ordering and permission writes."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from flaskr.command import update_shifu_demo as demo
from flaskr.dao import db
from flaskr.service.shifu.models import AiCourseAuth
from flaskr.service.user.models import UserInfo

from tests.service.billing.test_billing_callbacks import (
    billing_callback_app as demo_app,
)

__all__ = ["demo_app"]


@pytest.fixture
def demo_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    command_file = tmp_path / "flaskr/command/update_shifu_demo.py"
    command_file.parent.mkdir(parents=True)
    command_file.touch()
    directory = tmp_path / "demo_shifus"
    directory.mkdir()
    content = b'{"title": "Demonstration"}'
    (directory / "course.json").write_bytes(content)
    monkeypatch.setattr(demo, "__file__", str(command_file))
    return SimpleNamespace(content=content, digest=hashlib.sha256(content).hexdigest())


@pytest.mark.parametrize("existing", [None, "existing-course"])
def test_demo_import_reads_bytes_publishes_synchronously_then_updates_config(
    demo_files: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    existing: str | None,
) -> None:
    configuration = {"COURSE": existing, "HASH": "old"}
    monkeypatch.setattr(
        demo, "get_config", lambda key, _default: configuration.get(key)
    )
    events = []
    app = Flask(__name__)

    def import_file(
        received_app: Flask, course: str | None, file: object, owner: str
    ) -> str:
        assert received_app is app
        assert course == existing
        assert file.read() == demo_files.content
        assert file.filename == "course.json"
        assert owner == "system"
        events.append("import")
        return "new-course"

    def publish(
        received_app: Flask,
        owner: str,
        course: str,
        message: str,
        *,
        sync_summary: bool,
    ) -> None:
        assert received_app is app
        assert (owner, course, message, sync_summary) == (
            "system",
            "new-course",
            "",
            True,
        )
        events.append("publish")

    monkeypatch.setattr(demo, "import_shifu", import_file)
    monkeypatch.setattr(demo, "publish_shifu_draft", publish)
    upsert = Mock(side_effect=lambda *_args: events.append("config"))
    monkeypatch.setattr(demo, "_upsert_config", upsert)
    assert (
        demo._process_demo_shifu(
            app, "course.json", "COURSE", "course remark", "HASH", "hash remark"
        )
        == "new-course"
    )
    assert events == ["import", "publish", "config", "config"]
    assert upsert.call_args_list[0].args == (
        app,
        "COURSE",
        "new-course",
        "course remark",
    )
    assert upsert.call_args_list[1].args == (
        app,
        "HASH",
        demo_files.digest,
        "hash remark",
    )


def test_unchanged_demo_hash_does_not_import_publish_or_mutate_configuration(
    demo_files: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = {"COURSE": "course", "HASH": demo_files.digest}
    monkeypatch.setattr(
        demo, "get_config", lambda key, _default: configuration.get(key)
    )
    importer, publisher, upsert = Mock(), Mock(), Mock()
    monkeypatch.setattr(demo, "import_shifu", importer)
    monkeypatch.setattr(demo, "publish_shifu_draft", publisher)
    monkeypatch.setattr(demo, "_upsert_config", upsert)
    assert (
        demo._process_demo_shifu(
            Flask(__name__), "course.json", "COURSE", "course", "HASH", "hash"
        )
        == "course"
    )
    importer.assert_not_called()
    publisher.assert_not_called()
    upsert.assert_not_called()


@pytest.mark.usefixtures("demo_files")
@pytest.mark.parametrize("failure", ["import", "publish"])
def test_failed_import_or_publication_does_not_mark_hash_as_applied(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    monkeypatch.setattr(demo, "get_config", lambda *_args: None)
    importer = Mock(return_value="course")
    publisher = Mock()
    upsert = Mock()
    (importer if failure == "import" else publisher).side_effect = RuntimeError(
        "failed operation"
    )
    monkeypatch.setattr(demo, "import_shifu", importer)
    monkeypatch.setattr(demo, "publish_shifu_draft", publisher)
    monkeypatch.setattr(demo, "_upsert_config", upsert)
    with pytest.raises(RuntimeError, match="failed operation"):
        demo._process_demo_shifu(
            Flask(__name__), "course.json", "COURSE", "course", "HASH", "hash"
        )
    upsert.assert_not_called()
    if failure == "import":
        publisher.assert_not_called()


@pytest.mark.parametrize("exists", [False, True])
def test_demo_config_is_added_only_when_update_finds_no_existing_row(
    monkeypatch: pytest.MonkeyPatch,
    exists: bool,
) -> None:
    app = Flask(__name__)
    update, add = Mock(return_value=exists), Mock()
    monkeypatch.setattr(demo, "update_config", update)
    monkeypatch.setattr(demo, "add_config", add)
    demo._upsert_config(app, "KEY", "value", "remark")
    update.assert_called_once_with(
        app, "KEY", "value", is_secret=False, remark="remark"
    )
    if exists:
        add.assert_not_called()
    else:
        add.assert_called_once_with(
            app, "KEY", "value", is_secret=False, remark="remark"
        )


def test_demo_permissions_are_idempotent_and_only_apply_to_teachers(
    demo_app: Flask,
) -> None:
    db.session.add_all(
        [
            UserInfo(user_bid="teacher-new", is_creator=1),
            UserInfo(user_bid="teacher-existing", is_creator=1),
            UserInfo(user_bid="learner", is_creator=0),
            AiCourseAuth(
                course_auth_id="auth",
                course_id="course",
                user_id="teacher-existing",
                auth_type='["edit"]',
                status=0,
            ),
        ]
    )
    db.session.commit()
    demo._ensure_creator_permissions(demo_app, "course")
    db.session.flush()
    demo._ensure_creator_permissions(demo_app, "course")
    db.session.commit()
    db.session.expire_all()
    rows = AiCourseAuth.query.filter_by(course_id="course").all()
    assert {row.user_id for row in rows} == {"teacher-new", "teacher-existing"}
    assert all(
        row.status == 1 and json.loads(row.auth_type) == ["view"] for row in rows
    )


def test_demo_command_uses_independent_course_transactions(
    demo_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "get_env_config", lambda _key: False)
    permissions = Mock()
    monkeypatch.setattr(demo, "_ensure_creator_permissions", permissions)

    def process(_app: Flask, filename: str, *_args: str) -> str:
        user_bid = "teacher-cn" if filename == "cn_demo.json" else "teacher-en"
        db.session.add(UserInfo(user_bid=user_bid))
        db.session.flush()
        if filename == "en_demo.json":
            message = "English import failed"
            raise RuntimeError(message)
        return "cn-course"

    monkeypatch.setattr(demo, "_process_demo_shifu", process)
    with pytest.raises(RuntimeError, match="English import failed"):
        demo.update_demo_shifu(demo_app)
    db.session.expire_all()
    assert UserInfo.query.filter_by(user_bid="teacher-cn").count() == 1
    assert UserInfo.query.filter_by(user_bid="teacher-en").count() == 0
    permissions.assert_called_once_with(demo_app, "cn-course")


def test_demo_command_processes_both_languages_or_respects_skip(
    demo_app: Flask,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processor = Mock(side_effect=["cn-course", "en-course"])
    permissions = Mock()
    monkeypatch.setattr(demo, "_process_demo_shifu", processor)
    monkeypatch.setattr(demo, "_ensure_creator_permissions", permissions)
    monkeypatch.setattr(demo, "get_env_config", lambda _key: True)
    demo.update_demo_shifu(demo_app)
    processor.assert_not_called()
    monkeypatch.setattr(demo, "get_env_config", lambda _key: False)
    demo.update_demo_shifu(demo_app)
    assert [call.args[1] for call in processor.call_args_list] == [
        "cn_demo.json",
        "en_demo.json",
    ]
    assert [call.args[1] for call in permissions.call_args_list] == [
        "cn-course",
        "en-course",
    ]
