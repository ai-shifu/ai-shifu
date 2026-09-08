"""Regression tests for the arena's external publication and vote boundary."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from markdownflow_arena_lib.feishu import (  # noqa: E402
    OUTCOMES,
    FeishuPublisher,
    LarkCli,
    LarkCliError,
)


def _completed(
    stdout: object, *, code: int = 0, stderr: object = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, json.dumps(stdout), json.dumps(stderr))


@pytest.fixture
def publisher() -> FeishuPublisher:
    state = {
        "run_id": "run_123",
        "base_token": "base_123",
        "tables": {
            "matchups": "tblMatchups",
            "votes": "tblVotes",
            "summary": "tblSummary",
        },
        "permissions_verified": True,
    }
    result = FeishuPublisher({}, state, Mock())
    result.cli = Mock(spec=LarkCli)
    return result


def test_cli_uses_stdin_and_never_shell_interpolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(return_value=_completed({"ok": True, "data": {"id": "record"}}))
    monkeypatch.setattr(subprocess, "run", execute)
    body = {"text": "$(touch /tmp/unsafe) `secret`\nquotation's"}
    assert LarkCli().run(
        ["api", "PUT", "/example"], payload=body, payload_flag="--data"
    ) == {"id": "record"}
    args, kwargs = execute.call_args
    assert args[0] == [
        "lark-cli",
        "api",
        "PUT",
        "/example",
        "--as",
        "user",
        "--format",
        "json",
        "--data",
        "-",
    ]
    assert json.loads(kwargs["input"]) == body
    assert kwargs.get("shell", False) is False
    assert kwargs["timeout"] == 120


def test_missing_remote_attachment_invalidates_ready_before_repair(
    publisher: FeishuPublisher,
    tmp_path: Path,
) -> None:
    page = tmp_path / "page.png"
    page.write_bytes(b"verified image bytes")
    publisher.state["publication_ready_at"] = {"pair1": "2026-01-01T00:00:00Z"}
    publisher._attachment_rows = Mock(return_value=[])
    publisher._base = Mock(side_effect=LarkCliError("Synthetic upload failure"))
    with pytest.raises(LarkCliError, match="Synthetic upload"):
        publisher._attachments("pair1", "rec1", "a", {"render": {"pages": [str(page)]}})
    assert publisher.get_publication_ready_at("pair1") is None


def test_intact_verified_pdf_survives_local_metadata_only_change(
    publisher: FeishuPublisher,
    tmp_path: Path,
) -> None:
    pdf = tmp_path / "complete.pdf"
    pdf.write_bytes(b"new creation time with the same verified PNG pages")
    old_name = "A-001-" + "a" * 20 + ".pdf"
    ready = "2026-01-01T00:00:00Z"
    publisher.state["publication_ready_at"] = {"pair1": ready}
    publisher.state["publication_attachment_names"] = {"pair1": {"a_pdf": [old_name]}}
    publisher._attachment_rows = Mock(
        side_effect=lambda _matchup_id, field: (
            [{"name": old_name}] if field == publisher.fields["a_pdf"] else []
        )
    )
    publisher._base = Mock()
    publisher._attachments("pair1", "rec1", "a", {"render": {"pdf": str(pdf)}})
    assert publisher.get_publication_ready_at("pair1") == ready
    publisher._base.assert_not_called()


def test_cli_shortcut_json_uses_private_relative_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        path = Path(kwargs["cwd"]) / argv[-1].removeprefix("@")
        captured["path"] = path
        assert path.stat().st_mode & 0o777 == 0o600
        assert json.loads(path.read_text()) == {"text": "quotes ' and $()"}
        return _completed({"ok": True, "data": {}})

    monkeypatch.setattr(subprocess, "run", execute)
    LarkCli().run(["base", "+record-upsert"], payload={"text": "quotes ' and $()"})
    assert not captured["path"].exists()


@pytest.mark.parametrize("envelope", [{"data": {}}, {"ok": False, "data": {}}])
def test_cli_does_not_accept_exit_zero_without_ok_true(
    monkeypatch: pytest.MonkeyPatch, envelope: dict
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(return_value=_completed(envelope)))
    with pytest.raises(LarkCliError, match="ok=true") as error:
        LarkCli().run(["base", "+record-upsert"])
    assert error.value.uncertain


def test_cli_preserves_confirmation_exit_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        return_value=_completed(
            {},
            code=10,
            stderr={
                "ok": False,
                "error": {
                    "subtype": "confirmation_required",
                    "message": "secret token",
                },
            },
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(LarkCliError, match="exit 10") as error:
        LarkCli().run(["base", "+role-update"])
    assert error.value.exit_code == 10
    assert error.value.subtype == "confirmation_required"
    assert "secret" not in str(error.value)
    execute.assert_called_once()
    assert "--yes" not in execute.call_args.args[0]


def test_cli_rejects_success_when_required_fields_were_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        return_value=_completed(
            {
                "ok": True,
                "data": {
                    "record": {
                        "record_id": "rec1",
                        "ignored_fields": [{"reason": "READONLY"}],
                    }
                },
            }
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(LarkCliError, match="ignored requested fields") as error:
        LarkCli().run(["base", "+record-upsert"])
    assert error.value.uncertain


def test_timeout_is_uncertain_and_does_not_echo_private_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        side_effect=subprocess.TimeoutExpired(
            "sensitive command", 120, output="private prompt"
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(LarkCliError, match="may have completed") as error:
        LarkCli().run(["base", "+record-upsert"])
    assert error.value.uncertain
    assert error.value.subtype == "timeout"
    assert "private prompt" not in str(error.value)
    execute.assert_called_once()


def test_preflight_accepts_only_verified_user_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        return_value=_completed(
            {
                "identity": "user",
                "verified": True,
                "identities": {
                    "user": {"status": "ready", "verified": True, "token": "private"}
                },
            }
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    assert LarkCli().preflight() == {
        "identity": "user",
        "verified": True,
        "workflow_quota": None,
    }
    assert execute.call_args.args[0] == [
        "lark-cli",
        "auth",
        "status",
        "--json",
        "--verify",
    ]


def test_preflight_accepts_a_verified_refreshed_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        return_value=_completed(
            {
                "identity": "user",
                "verified": True,
                "identities": {
                    "user": {
                        "status": "needs_refresh",
                        "tokenStatus": "needs_refresh",
                        "verified": True,
                    }
                },
            }
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    assert LarkCli().preflight()["verified"] is True


def test_preflight_rejects_successful_bot_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = Mock(
        return_value=_completed(
            {
                "identity": "bot",
                "verified": True,
                "identities": {
                    "user": {"status": "verify_failed", "verified": False},
                    "bot": {"verified": True},
                },
            }
        )
    )
    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(LarkCliError, match="user authentication"):
        LarkCli().preflight()


def test_ndjson_reads_all_pages_without_treating_manifest_as_write_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offsets = []

    def execute(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        offset = int(argv[argv.index("--offset") + 1])
        offsets.append(offset)
        rows = [
            {"record_id": f"rec{index}"}
            for index in range(offset, offset + (2 if offset == 0 else 1))
        ]
        (Path(kwargs["cwd"]) / "records.ndjson").write_text(
            "\n".join(json.dumps(row) for row in rows)
        )
        return _completed({"records_count": len(rows), "has_more": offset == 0})

    monkeypatch.setattr(subprocess, "run", execute)
    assert LarkCli().records(["base", "+record-list"]) == [
        {"record_id": "rec0"},
        {"record_id": "rec1"},
        {"record_id": "rec2"},
    ]
    assert offsets == [0, 2]


def test_public_schema_contains_no_models_or_prompts(
    publisher: FeishuPublisher,
) -> None:
    schema = publisher._schema("matchups")
    assert len([field for field in schema if field["type"] == "button"]) == 4
    assert {field["name"] for field in schema} == {
        publisher.fields[key]
        for key in (
            "matchup_id",
            "run_id",
            "case_id",
            "task_description",
            "category",
            "instructions",
            "a_images",
            "b_images",
            "a_pdf",
            "b_pdf",
        )
    } | set(publisher.copy["choices"].values())


@pytest.mark.parametrize("outcome", OUTCOMES)
def test_workflows_append_votes_with_click_actor_not_record_creator(
    publisher: FeishuPublisher, outcome: str
) -> None:
    workflow = publisher._workflow(outcome)
    trigger, action = workflow["steps"]
    assert trigger["type"] == "ButtonTrigger"
    assert action["type"] == "AddRecordAction"
    assert trigger["title"] == publisher.copy["workflow_trigger_title"]
    assert action["title"] == publisher.copy["workflow_action_title"]
    fields = {
        item["field_name"]: item["value"][0] for item in action["data"]["field_values"]
    }
    assert fields[publisher.fields["reviewer"]] == {
        "value_type": "ref",
        "value": "$.click.user",
    }
    assert fields[publisher.fields["matchup_record_id"]]["value"] == "$.click.recordId"
    assert fields[publisher.fields["voted_at"]]["value"] == "$.click.time"
    assert fields[publisher.fields["choice"]] == {
        "value_type": "text",
        "value": outcome,
    }
    assert "created_by" not in json.dumps(workflow)
    assert "recordCreatedUser" not in json.dumps(workflow)


def test_organization_editing_removes_only_dedicated_base_advanced_permissions(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.run.side_effect = [
        {"base": {"is_advanced": True}},
        {},
        {"base": {"is_advanced": False}},
    ]
    publisher._configure_permissions()
    calls = [call.args[0] for call in publisher.cli.run.call_args_list]
    assert calls[1] == ["base", "+advperm-disable", "--base-token", "base_123", "--yes"]
    assert publisher.state["permission_mode"] == "organization_editable"
    assert publisher.state["permissions_verified"] is True
    assert not any("role" in item for call in calls for item in call)


def test_already_ordinary_permissions_require_no_permission_write(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.run.return_value = {"base": {"is_advanced": False}}
    publisher._configure_permissions()
    publisher.cli.run.assert_called_once()


def test_unconfirmed_advanced_permission_disable_fails_closed(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.run.side_effect = [
        {"base": {"is_advanced": True}},
        {},
        {"base": {"is_advanced": True}},
    ]
    with pytest.raises(LarkCliError, match="link sharing remains closed"):
        publisher._configure_permissions()


def test_permission_mode_is_explicit_and_has_no_silent_fallback() -> None:
    with pytest.raises(ValueError, match="organization_editable"):
        FeishuPublisher({"permission_mode": "strict"}, {}, Mock())


def test_feishu_preflight_reports_organization_editing_mode(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.preflight.return_value = {"identity": "user", "verified": True}
    assert publisher.preflight() == {
        "identity": "user",
        "verified": True,
        "permission_mode": "organization_editable",
    }


def test_workflow_listing_missing_items_is_not_an_empty_arena(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.run.return_value = {}
    with pytest.raises(LarkCliError, match="listing is incomplete"):
        publisher._ensure_workflows()
    publisher.cli.run.assert_called_once()


def test_retry_adopts_existing_machine_id_after_unknown_create(
    publisher: FeishuPublisher,
) -> None:
    values = {
        publisher.fields["matchup_id"]: "matchup1",
        publisher.fields["run_id"]: "run_123",
    }
    publisher.cli.records.side_effect = [[], [{"record_id": "recRecovered", **values}]]
    publisher.cli.run.side_effect = [LarkCliError("timeout", uncertain=True), {}]
    with pytest.raises(LarkCliError, match="timeout"):
        publisher._record("matchups", "matchup1", values)
    assert "record:matchups:matchup1" in publisher.state["pending"]
    assert publisher._record("matchups", "matchup1", values) == "recRecovered"
    commands = [call.args[0] for call in publisher.cli.run.call_args_list]
    assert sum("--record-id" not in command for command in commands) == 1
    assert publisher.state["records"]["matchups"]["matchup1"] == "recRecovered"
    assert publisher.state["pending"] == {}


def test_unknown_create_without_visible_record_never_blindly_retries(
    publisher: FeishuPublisher,
) -> None:
    publisher.state["pending"] = {"record:matchups:matchup1": True}
    publisher.cli.records.return_value = []
    with pytest.raises(LarkCliError, match="no duplicate"):
        publisher._record(
            "matchups", "matchup1", {publisher.fields["matchup_id"]: "matchup1"}
        )
    publisher.cli.run.assert_not_called()


@pytest.mark.parametrize("table", ["matchups", "summary"])
def test_empty_query_with_known_record_id_never_creates_a_duplicate(
    publisher: FeishuPublisher, table: str
) -> None:
    publisher.state["records"] = {table: {"machine1": "recAlreadyCreated"}}
    publisher.cli.records.return_value = []
    with pytest.raises(LarkCliError, match="known arena record") as error:
        publisher._record(table, "machine1", {})
    assert error.value.subtype == "missing_known_record"
    assert publisher.state["records"][table]["machine1"] == "recAlreadyCreated"
    publisher.cli.run.assert_not_called()
    publisher.save_state.assert_not_called()


def test_record_create_parses_live_single_record_id_list(
    publisher: FeishuPublisher,
) -> None:
    values = {
        publisher.fields["matchup_id"]: "matchup1",
        publisher.fields["run_id"]: "run_123",
    }
    publisher.cli.records.return_value = []
    publisher.cli.run.return_value = {
        "record": {"record_id_list": ["recCreated"]},
        "created": True,
    }
    assert publisher._record("matchups", "matchup1", values) == "recCreated"
    assert publisher.state["pending"] == {}
    publisher.cli.run.assert_called_once()
    publisher.cli.records.assert_called_once()


def test_record_create_rejects_multiple_returned_ids(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.records.return_value = []
    publisher.cli.run.return_value = {
        "record": {"record_id_list": ["rec1", "rec2"]},
        "created": True,
    }
    with pytest.raises(LarkCliError, match="one created record ID"):
        publisher._record("matchups", "matchup1", {})
    assert publisher.state["pending"] == {"record:matchups:matchup1": True}


def test_successful_create_without_unique_readback_remains_pending(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.records.return_value = []
    publisher.cli.run.return_value = {"record": {}, "created": True}
    with pytest.raises(LarkCliError, match="one created record"):
        publisher._record("matchups", "matchup1", {})
    assert publisher.state["pending"] == {"record:matchups:matchup1": True}


def test_record_business_key_is_not_a_database_unique_constraint(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.records.return_value = [{"record_id": "rec1"}, {"record_id": "rec2"}]
    with pytest.raises(LarkCliError, match="Duplicate"):
        publisher._record("matchups", "matchup1", {})
    publisher.cli.run.assert_not_called()


def test_record_from_another_run_is_never_overwritten(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.records.return_value = [
        {"record_id": "rec1", publisher.fields["run_id"]: "foreign"}
    ]
    with pytest.raises(LarkCliError, match="different run"):
        publisher._record("matchups", "matchup1", {})
    publisher.cli.run.assert_not_called()


def test_upload_names_do_not_reveal_model_and_resume_does_not_append_twice(
    publisher: FeishuPublisher, tmp_path: Path
) -> None:
    source = tmp_path / "secret-model-full-prompt.png"
    source.write_bytes(b"PNG fixture")
    uploaded = []
    artifact = {
        "artifact_id": "artifact-private-model",
        "render": {"pages": [str(source)]},
    }
    matchup_key = publisher.fields["matchup_id"]
    image_key = publisher.fields["a_images"]

    def records(_args: list[str]) -> list[dict]:
        return [
            {
                "record_id": "rec1",
                matchup_key: "matchup1",
                image_key: [{"name": name} for name in uploaded] if uploaded else None,
            }
        ]

    def run(argv: list[str], **kwargs: object) -> dict:
        assert "+record-upload-attachment" in argv
        filenames = [
            argv[index + 1] for index, item in enumerate(argv) if item == "--file"
        ]
        for name in filenames:
            assert "secret" not in name
            assert "model" not in name
            assert (Path(kwargs["cwd"]) / name).read_bytes() == b"PNG fixture"
        uploaded.extend(filenames)
        return {}

    publisher.cli.records.side_effect = records
    publisher.cli.run.side_effect = run
    publisher._attachments("matchup1", "rec1", "a", artifact)
    publisher._attachments("matchup1", "rec1", "a", artifact)
    assert len(uploaded) == 1
    publisher.cli.run.assert_called_once()
    assert publisher.state["pending"] == {}


def test_fetch_votes_keeps_individual_actors_and_duplicate_clicks(
    publisher: FeishuPublisher,
) -> None:
    publisher.state["records"] = {"matchups": {"matchup1": "recPair"}}
    raw = {
        publisher.fields["run_id"]: "run_123",
        publisher.fields["matchup_record_id"]: "recPair",
        publisher.fields["reviewer"]: [
            {"id": "ou_actual_clicker", "name": "Private name"}
        ],
        publisher.fields["choice"]: "a",
        publisher.fields["voted_at"]: "2026-09-08T09:00:00.000+08:00",
        "created_by": [{"id": "ou_owner"}],
    }
    publisher.cli.records.return_value = [
        {"record_id": "recVote1", **raw},
        {"record_id": "recVote2", **raw},
    ]
    votes = publisher.fetch_votes()
    assert len(votes) == 2
    assert all(vote["reviewer_id"] == "ou_actual_clicker" for vote in votes)
    assert all(vote["matchup_id"] == "matchup1" for vote in votes)
    assert all(vote["created_at"] == "2026-09-08T01:00:00Z" for vote in votes)
    assert "Private name" not in json.dumps(votes)


@pytest.mark.parametrize(
    "reviewers",
    [
        None,
        "x",
        1,
        {"id": "ou_other_shape"},
        ["x"],
        [None],
        [{}],
        [{"id": None}],
        [{"id": 7}],
        [{"id": " "}],
        [{"id": "ou_first"}, {"id": "ou_second"}],
    ],
)
def test_fetch_votes_keeps_malformed_actor_rows_unscorable(
    publisher: FeishuPublisher, reviewers: object
) -> None:
    publisher.cli.records.return_value = [
        {
            "record_id": "recMalformed",
            publisher.fields["reviewer"]: reviewers,
            publisher.fields["voted_at"]: "2026-09-08T01:00:00Z",
            "created_by": [{"id": "ou_owner"}],
        },
        {
            "record_id": "recValid",
            publisher.fields["reviewer"]: [{"id": "ou_clicker"}],
        },
    ]
    votes = publisher.fetch_votes()
    assert [vote["vote_id"] for vote in votes] == ["recMalformed", "recValid"]
    assert votes[0]["reviewer_id"] is None
    assert votes[1]["reviewer_id"] == "ou_clicker"


@pytest.mark.parametrize(
    "row", [{}, {"record_id": None}, {"record_id": []}, {"record_id": " "}, None]
)
def test_fetch_votes_skips_rows_without_a_native_record_identity(
    publisher: FeishuPublisher, row: object
) -> None:
    publisher.cli.records.return_value = [row, {"record_id": "recNext"}]
    assert [vote["vote_id"] for vote in publisher.fetch_votes()] == ["recNext"]


def test_fetch_votes_normalizes_unhashable_comparison_fields(
    publisher: FeishuPublisher,
) -> None:
    publisher.cli.records.return_value = [
        {
            "record_id": "recMalformed",
            publisher.fields["reviewer"]: [{"id": "ou_clicker"}],
            publisher.fields["matchup_record_id"]: ["recPair"],
            publisher.fields["run_id"]: {},
            publisher.fields["choice"]: ["a"],
        }
    ]
    vote = publisher.fetch_votes()[0]
    assert vote["matchup_record_id"] is None
    assert vote["matchup_id"] is None
    assert vote["choice"] is None
    assert vote["run_id"] is None


def test_failed_permission_verification_never_opens_link(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    sharing = Mock()
    monkeypatch.setattr(publisher, "_ensure_base", Mock())
    monkeypatch.setattr(publisher, "_ensure_tables", Mock())
    monkeypatch.setattr(publisher, "_sharing", sharing)
    monkeypatch.setattr(
        publisher,
        "_configure_permissions",
        Mock(side_effect=LarkCliError("permission mismatch")),
    )
    enable = Mock()
    monkeypatch.setattr(publisher, "_ensure_workflows", enable)
    with pytest.raises(LarkCliError, match="permission mismatch"):
        publisher.provision("run_123")
    sharing.assert_called_once_with(open_link=False)
    enable.assert_not_called()


def test_summary_does_not_upload_prompts_or_raw_reviewer_data(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = Mock(return_value="recSummary")
    monkeypatch.setattr(publisher, "_record", record)
    publisher.publish_summary(
        {
            "run_id": "run_123",
            "valid_vote_count": 2,
            "source_prompt": "private prompt",
            "matchup_model_mapping": {"matchup1": {"a": "private-model-name"}},
            "models": [
                {
                    "model": "private-model-name",
                    "wins": 1,
                    "render_failed": 2,
                    "truncated": 3,
                    "input_mismatch": 4,
                    "source_prompt": "nested private prompt",
                }
            ],
            "accepted_votes": [{"reviewer_id": "ou_private"}],
        }
    )
    table, machine_id, fields = record.call_args.args
    assert table == "summary"
    assert machine_id == "summary:run_123"
    body = fields[publisher.fields["summary"]]
    assert "private prompt" not in body
    assert "ou_private" not in body
    assert "matchup1" not in body
    assert json.loads(body)["valid_vote_count"] == 2
    model = json.loads(body)["models"][0]
    assert {
        key: model[key] for key in ("render_failed", "truncated", "input_mismatch")
    } == {"render_failed": 2, "truncated": 3, "input_mismatch": 4}


def test_all_supported_locales_have_matching_copy_keys(
    publisher: FeishuPublisher,
) -> None:
    for locale in ("zh-CN", "en-US", "fr-FR", "ar-SA", "th-TH"):
        translated = FeishuPublisher(
            {"locale": locale}, copy.deepcopy(publisher.state), Mock()
        )
        assert translated.fields.keys() == publisher.fields.keys()
        assert translated.copy["choices"].keys() == publisher.copy["choices"].keys()


def test_chinese_copy_preserves_the_requested_table_and_button_names(
    publisher: FeishuPublisher,
) -> None:
    assert publisher.copy["tables"] == {
        "matchups": "待评审对局",
        "votes": "原始投票",
        "summary": "管理与统计",
    }
    assert list(publisher.copy["choices"].values()) == [
        "A 更好",
        "B 更好",
        "差不多",
        "都不好",
    ]


def test_matchup_publication_uses_explicit_blind_allowlist(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    def save_record(table: str, machine_id: str, _values: dict) -> str:
        publisher.state.setdefault("records", {}).setdefault(table, {})[machine_id] = (
            "recPair"
        )
        return "recPair"

    record = Mock(side_effect=save_record)
    attachments = Mock()
    monkeypatch.setattr(publisher, "_record", record)
    monkeypatch.setattr(publisher, "_attachments", attachments)
    matchup = {
        "matchup_id": "matchup1",
        "case_id": "case1",
        "task_description": "Private internal implementation task",
        "category": "slides",
        "a_artifact_id": "artifactA",
        "b_artifact_id": "artifactB",
        "source_prompt": "private prompt",
    }
    artifact_a = {
        "artifact_id": "artifactA",
        "status": "complete",
        "case_id": "case1",
        "model": {"model": "private model"},
        "render": {"pages": ["/image.png"], "sha256": {"/image.png": "0" * 64}},
    }
    artifact_b = {**artifact_a, "artifact_id": "artifactB"}
    assert publisher.publish_matchup(matchup, artifact_a, artifact_b) == "recPair"
    payload = json.dumps(record.call_args.args[2])
    assert "private prompt" not in payload
    assert "private model" not in payload
    assert "Private internal implementation task" not in payload
    fields = record.call_args.args[2]
    assert (
        fields[publisher.fields["task_description"]]
        == publisher.copy["review_tasks"]["slides"]
    )
    assert (
        fields[publisher.fields["category"]]
        == publisher.copy["category_labels"]["slides"]
    )
    assert "artifactA" not in payload
    ready = publisher.get_publication_ready_at("matchup1")
    assert ready
    assert ready.endswith("Z")
    publisher.publish_matchup(matchup, artifact_a, artifact_b)
    assert publisher.get_publication_ready_at("matchup1") == ready
    assert attachments.call_count == 4


def test_failed_attachment_upload_never_marks_matchup_ready(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publisher, "_record", Mock(return_value="recPair"))
    monkeypatch.setattr(
        publisher,
        "_attachments",
        Mock(side_effect=[None, LarkCliError("upload failed")]),
    )
    matchup = {
        "matchup_id": "pair1",
        "case_id": "case1",
        "category": "text",
        "a_artifact_id": "artifactA",
        "b_artifact_id": "artifactB",
    }
    artifact = {
        "artifact_id": "artifactA",
        "case_id": "case1",
        "status": "complete",
        "render": {"pages": ["/image.png"], "sha256": {"/image.png": "0" * 64}},
    }
    with pytest.raises(LarkCliError, match="upload failed"):
        publisher.publish_matchup(
            matchup, artifact, {**artifact, "artifact_id": "artifactB"}
        )
    assert publisher.get_publication_ready_at("pair1") is None


def test_new_render_revision_invalidates_old_readiness_until_replacement_finishes(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = Mock(return_value="recPair")
    monkeypatch.setattr(publisher, "_record", record)
    monkeypatch.setattr(publisher, "_attachments", Mock())
    monkeypatch.setattr(
        "markdownflow_arena_lib.feishu.utc_now", lambda: "2026-09-08T01:00:00Z"
    )
    matchup = {
        "matchup_id": "pair1",
        "case_id": "case1",
        "a_artifact_id": "artifactA",
        "b_artifact_id": "artifactB",
    }
    a = {
        "artifact_id": "artifactA",
        "case_id": "case1",
        "status": "complete",
        "render": {"pages": ["/a.png"], "sha256": {"/a.png": "a" * 64}},
    }
    b = {**a, "artifact_id": "artifactB"}
    publisher.publish_matchup(matchup, a, b)
    old_revision = publisher.state["publication_render_fingerprints"]["pair1"]
    a = {**a, "render": {"pages": ["/a.png"], "sha256": {"/a.png": "b" * 64}}}
    monkeypatch.setattr(
        publisher, "_attachments", Mock(side_effect=LarkCliError("upload failed"))
    )
    with pytest.raises(LarkCliError, match="upload failed"):
        publisher.publish_matchup(matchup, a, b)
    assert publisher.get_publication_ready_at("pair1") is None
    assert publisher.state["publication_render_fingerprints"]["pair1"] == old_revision
    monkeypatch.setattr(publisher, "_attachments", Mock())
    monkeypatch.setattr(
        "markdownflow_arena_lib.feishu.utc_now", lambda: "2026-09-08T02:00:00Z"
    )
    assert publisher.publish_matchup(matchup, a, b) == "recPair"
    assert publisher.get_publication_ready_at("pair1") == "2026-09-08T02:00:00Z"
    assert publisher.state["publication_render_fingerprints"]["pair1"] != old_revision


def test_attachment_replacement_removes_only_old_neutral_files_and_reads_back(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = tmp_path / "new.png"
    page.write_bytes(b"new PNG revision")
    name = publisher.fields["a_images"]
    old_name = "A-001-" + "a" * 20 + ".png"
    cells = {name: [{"name": old_name, "file_token": "oldToken"}]}
    publisher.state["pending"] = {f"attachment:rec1:a_images:{old_name}": True}
    monkeypatch.setattr(
        publisher, "_attachment_rows", lambda _mid, field: list(cells.get(field, []))
    )
    operations = []

    def run(args: list[str], **_kwargs: object) -> dict:
        operations.append(args[1])
        if args[1] == "+record-remove-attachment":
            assert args[-2:] == ["--file-token", "oldToken"]
            assert "--yes" in args
            cells[name] = []
        else:
            assert args[1] == "+record-upload-attachment"
            filename = args[args.index("--file") + 1]
            assert filename != old_name
            cells[name] = [{"name": filename, "file_token": "newToken"}]
        return {}

    publisher.cli.run.side_effect = run
    publisher._attachments("pair1", "rec1", "a", {"render": {"pages": [str(page)]}})
    assert operations == ["+record-remove-attachment", "+record-upload-attachment"]
    assert publisher.state["pending"] == {}


def test_attachment_replacement_refuses_to_delete_unrecognized_user_files(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        publisher,
        "_attachment_rows",
        lambda *_args: [{"name": "reviewer notes.pdf", "file_token": "userToken"}],
    )
    with pytest.raises(LarkCliError, match="unrecognized attachment"):
        publisher._attachments("pair1", "rec1", "a", {"render": {"pages": []}})
    publisher.cli.run.assert_not_called()


def test_attachment_propagation_delay_retries_reads_without_reuploading(
    publisher: FeishuPublisher, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = tmp_path / "page.png"
    page.write_bytes(b"PNG content")
    progress = {"reads": 0, "filename": None}

    def rows(_matchup_id: str, field: str) -> list[dict]:
        if field != publisher.fields["a_images"]:
            return []
        progress["reads"] += 1
        if progress["reads"] <= 2:
            return []
        return [{"name": progress["filename"], "file_token": "uploadedToken"}]

    def upload(args: list[str], **_kwargs: object) -> dict:
        assert args[1] == "+record-upload-attachment"
        progress["filename"] = args[args.index("--file") + 1]
        return {}

    monkeypatch.setattr(publisher, "_attachment_rows", rows)
    publisher.cli.run.side_effect = upload
    publisher._attachments("pair1", "rec1", "a", {"render": {"pages": [str(page)]}})
    publisher.cli.run.assert_called_once()
    assert progress["reads"] == 3
    assert publisher.state["pending"] == {}


def test_changed_local_artwork_bytes_are_rejected_before_remote_replacement(
    publisher: FeishuPublisher, tmp_path: Path
) -> None:
    page = tmp_path / "page.png"
    page.write_bytes(b"changed after rendering")
    artifact = {"render": {"pages": [str(page)], "sha256": {str(page): "0" * 64}}}
    with pytest.raises(ValueError, match="no longer match"):
        publisher._attachments("pair1", "rec1", "a", artifact)
    publisher.cli.run.assert_not_called()
    publisher.cli.records.assert_not_called()


def test_failed_artifact_cannot_be_published_even_with_old_render(
    publisher: FeishuPublisher,
) -> None:
    matchup = {
        "matchup_id": "matchup1",
        "case_id": "case1",
        "a_artifact_id": "artifactA",
        "b_artifact_id": "artifactB",
    }
    failed = {
        "artifact_id": "artifactA",
        "status": "render_failed",
        "case_id": "case1",
        "render": {"pages": ["/old.png"]},
    }
    with pytest.raises(ValueError, match="incomplete"):
        publisher.publish_matchup(
            matchup, failed, {**failed, "artifact_id": "artifactB"}
        )
    publisher.cli.run.assert_not_called()


@pytest.mark.parametrize(
    "manager", ["collaborator_full_access", "collaborator_can_edit"]
)
def test_sharing_verifies_current_v2_permission_readback(
    publisher: FeishuPublisher, manager: str
) -> None:
    current = {"permission_public": {"link_share_entity": "closed"}}
    after = {
        "permission_public": {
            "comment_entity": "anyone_can_edit",
            "copy_entity": "only_full_access",
            "external_access_entity": "closed",
            "link_share_entity": "tenant_editable",
            "lock_switch": False,
            "manage_collaborator_entity": manager,
            "security_entity": "only_full_access",
            "share_entity": "same_tenant",
        }
    }
    publisher.cli.run.side_effect = [{"auth_result": True}, current, {}, after]
    if manager == "collaborator_full_access":
        publisher._sharing(open_link=True)
        assert publisher.state["shared"] is True
    else:
        with pytest.raises(LarkCliError, match="permission readback"):
            publisher._sharing(open_link=True)
        assert publisher.state.get("shared") is not True
