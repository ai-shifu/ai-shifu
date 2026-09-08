"""Publish blinded artwork and collect append-only votes in a dedicated Lark Base.

Only this module talks to lark-cli. It never sends messages, uploads source
prompts, or serializes an artifact/model configuration into the public table.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .state import publication_render_fingerprint, utc_now

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


OUTCOMES = ("a", "b", "tie", "both_bad")


class LarkCliError(RuntimeError):
    """A sanitized CLI failure, including whether a write may have succeeded."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        subtype: str = "unknown",
        uncertain: bool = False,
    ) -> None:
        """Keep machine-readable error context without storing raw CLI output."""
        super().__init__(message)
        self.exit_code = exit_code
        self.subtype = subtype
        self.uncertain = uncertain


def _object(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        message = f"Lark returned an invalid {context}; reconcile before retrying"
        raise LarkCliError(message, subtype="invalid_response", uncertain=True)
    return value


def _identifier(value: dict, *keys: str) -> str:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_-]+", candidate):
            return candidate
    message = "Lark response omitted a resource identifier; reconcile before retrying"
    raise LarkCliError(message, subtype="invalid_response", uncertain=True)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def _reject_ignored_fields(value: object) -> None:
    """Reject partly ignored writes or projections as unconfirmed arena results."""
    if isinstance(value, dict):
        if value.get("ignored_fields"):
            message = "Lark ignored requested fields; reconcile the schema and remote result before retrying"
            raise LarkCliError(message, subtype="ignored_fields", uncertain=True)
        for item in value.values():
            _reject_ignored_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_ignored_fields(item)


class LarkCli:
    """Invoke argv directly; never interpret shell text or automatically approve."""

    def __init__(self, executable: str = "lark-cli", timeout: float = 120) -> None:
        """Use the configured executable without spawning a shell."""
        self.executable = executable
        self.timeout = timeout

    def _execute(
        self, args: Sequence[str], *, stdin: str | None = None, cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [self.executable, *args],
                input=stdin,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            message = "Lark CLI timed out; the remote write may have completed. Reconcile before retrying"
            raise LarkCliError(message, subtype="timeout", uncertain=True) from None
        except OSError:
            message = "Lark CLI could not start; check its executable and permissions"
            raise LarkCliError(message, subtype="unavailable") from None

    @staticmethod
    def _decode(result: subprocess.CompletedProcess) -> dict:
        if result.returncode:
            try:
                envelope = json.loads(result.stderr)
            except (ValueError, TypeError):
                envelope = {}
            error = envelope.get("error", {}) if isinstance(envelope, dict) else {}
            subtype = (
                error.get("subtype", "unknown")
                if isinstance(error, dict)
                else "unknown"
            )
            # Do not repeat raw CLI output: it can contain submitted content or tokens.
            subtype = subtype if re.fullmatch(r"[a-z_]+", str(subtype)) else "unknown"
            if result.returncode == 10:
                message = "Lark CLI requires explicit confirmation (exit 10); no automatic retry was attempted"
                raise LarkCliError(
                    message, exit_code=10, subtype="confirmation_required"
                )
            message = f"Lark CLI failed (exit {result.returncode}, {subtype}); inspect the local operation state"
            raise LarkCliError(
                message, exit_code=result.returncode, subtype=subtype, uncertain=True
            )
        try:
            value = json.loads(result.stdout)
        except (ValueError, TypeError):
            message = "Lark CLI returned invalid JSON; reconcile the remote operation before retrying"
            raise LarkCliError(
                message, subtype="invalid_response", uncertain=True
            ) from None
        return _object(value, "JSON response")

    def run(
        self,
        args: Sequence[str],
        *,
        payload: object = None,
        payload_flag: str = "--json",
        cwd: Path | None = None,
    ) -> dict | list:
        """Return data only after an explicit successful CLI envelope.

        Native API --data supports stdin. Base shortcut JSON flags in CLI
        1.0.87 do not support '-' or '@-'; use a private relative input file.
        """
        argv = list(args)
        if "--as" not in argv:
            argv.extend(["--as", "user"])
        argv.extend(["--format", "json"])
        if payload is None:
            result = self._execute(argv, cwd=cwd)
        elif payload_flag == "--data":
            result = self._execute(
                [*argv, payload_flag, "-"],
                stdin=json.dumps(payload, ensure_ascii=False),
                cwd=cwd,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="arena-lark-input-") as directory:
                path = Path(directory) / "payload.json"
                path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                path.chmod(0o600)
                result = self._execute(
                    [*argv, payload_flag, "@payload.json"], cwd=path.parent
                )
        value = self._decode(result)
        if value.get("ok") is not True:
            message = "Lark CLI did not confirm ok=true; reconcile before retrying"
            raise LarkCliError(message, subtype="invalid_response", uncertain=True)
        data = value.get("data")
        _reject_ignored_fields(data)
        if isinstance(data, list):
            return data
        return _object(data, "data envelope")

    def preflight(self) -> dict:
        """Verify current user auth without logging credentials or changing auth."""
        value = self._decode(self._execute(["auth", "status", "--json", "--verify"]))
        user = value.get("identities", {}).get("user", {})
        # CLI status labels describe the stored token before verification. A
        # successful refresh can return status=needs_refresh and verified=true.
        # Inspect the user-specific verification, never a successful bot fallback.
        if user.get("verified") is not True:
            message = "Lark user authentication is not verified and ready"
            raise LarkCliError(message, subtype="authorization")
        return {"identity": "user", "verified": True, "workflow_quota": None}

    def records(self, args: Sequence[str]) -> list[dict]:
        """Read typed NDJSON pages, whose documented stdout is a bare manifest."""
        records = []
        offset = 0
        while True:
            with tempfile.TemporaryDirectory(prefix="arena-lark-read-") as directory:
                path = Path(directory) / "records.ndjson"
                result = self._execute(
                    [
                        *args,
                        "--as",
                        "user",
                        "--format",
                        "ndjson",
                        "--output",
                        "records.ndjson",
                        "--limit",
                        "2000",
                        "--offset",
                        str(offset),
                    ],
                    cwd=path.parent,
                )
                manifest = self._decode(result)
                # Unlike ordinary commands, this read-only export intentionally has no ok.
                if (
                    isinstance(manifest.get("data"), dict)
                    and manifest.get("ok") is True
                ):
                    manifest = manifest["data"]
                _reject_ignored_fields(manifest)
                count = manifest.get("records_count")
                if (
                    not isinstance(count, int)
                    or isinstance(count, bool)
                    or not isinstance(manifest.get("has_more"), bool)
                    or not path.is_file()
                ):
                    message = "Lark NDJSON export did not provide a complete manifest"
                    raise LarkCliError(message, subtype="invalid_response")
                rows = [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if len(rows) != count or any(not isinstance(row, dict) for row in rows):
                    message = "Lark NDJSON export count does not match its records"
                    raise LarkCliError(message, subtype="invalid_response")
                records.extend(rows)
                if not manifest["has_more"]:
                    return records
                if not count:
                    message = "Lark NDJSON pagination made no progress"
                    raise LarkCliError(message, subtype="invalid_response")
                offset += count


class FeishuPublisher:
    """Manage resources owned by one arena run, with durable retry journals."""

    def __init__(
        self, config: dict, state: dict, save_state: Callable[[], None]
    ) -> None:
        """Reuse and mutate the run manifest's Feishu section in place."""
        if (
            config.get("permission_mode", "organization_editable")
            != "organization_editable"
        ):
            message = "The arena supports only organization_editable permissions"
            raise ValueError(message)
        self.config = config
        self.state = state
        self.save_state = save_state
        self.cli = LarkCli(
            config.get("cli", "lark-cli"), timeout=config.get("timeout_seconds", 120)
        )
        locale = config.get("locale", "zh-CN")
        if locale not in {"zh-CN", "en-US", "fr-FR", "ar-SA", "th-TH"}:
            message = "Unsupported arena locale"
            raise ValueError(message)
        path = (
            Path(__file__).resolve().parents[3]
            / "i18n"
            / locale
            / "modules"
            / "arena.json"
        )
        document = json.loads(path.read_text(encoding="utf-8"))

        def _(key: str) -> str:
            current = document
            for part in key.removeprefix("module.arena.").split("."):
                current = current[part]
            if not isinstance(current, str):
                message = "Arena translation must be a string"
                raise TypeError(message)
            return current

        self.copy = {
            "base_name": _("module.arena.base_name"),
            "workflow_title": _("module.arena.workflow_title"),
            "workflow_trigger_title": _("module.arena.workflow_trigger_title"),
            "workflow_action_title": _("module.arena.workflow_action_title"),
            "instructions": _("module.arena.instructions"),
            "category_labels": {
                "text": _("module.arena.category_labels.text"),
                "visual": _("module.arena.category_labels.visual"),
                "slides": _("module.arena.category_labels.slides"),
            },
            "review_tasks": {
                "text": _("module.arena.review_tasks.text"),
                "visual": _("module.arena.review_tasks.visual"),
                "slides": _("module.arena.review_tasks.slides"),
            },
            "tables": {
                "matchups": _("module.arena.tables.matchups"),
                "votes": _("module.arena.tables.votes"),
                "summary": _("module.arena.tables.summary"),
            },
            "choices": {
                "a": _("module.arena.choices.a"),
                "b": _("module.arena.choices.b"),
                "tie": _("module.arena.choices.tie"),
                "both_bad": _("module.arena.choices.both_bad"),
            },
            "fields": {
                "matchup_id": _("module.arena.fields.matchup_id"),
                "run_id": _("module.arena.fields.run_id"),
                "case_id": _("module.arena.fields.case_id"),
                "task_description": _("module.arena.fields.task_description"),
                "category": _("module.arena.fields.category"),
                "instructions": _("module.arena.fields.instructions"),
                "a_images": _("module.arena.fields.a_images"),
                "b_images": _("module.arena.fields.b_images"),
                "a_pdf": _("module.arena.fields.a_pdf"),
                "b_pdf": _("module.arena.fields.b_pdf"),
                "matchup_record_id": _("module.arena.fields.matchup_record_id"),
                "reviewer": _("module.arena.fields.reviewer"),
                "choice": _("module.arena.fields.choice"),
                "voted_at": _("module.arena.fields.voted_at"),
                "summary_id": _("module.arena.fields.summary_id"),
                "summary": _("module.arena.fields.summary"),
            },
        }
        self.fields = self.copy["fields"]

    def preflight(self) -> dict:
        """Check read-only prerequisites; absent quota APIs remain explicitly unknown."""
        return {**self.cli.preflight(), "permission_mode": "organization_editable"}

    def _base(self, command: str, *args: str, **kwargs: object) -> dict | list:
        return self.cli.run(
            ["base", command, "--base-token", self.state["base_token"], *args], **kwargs
        )

    def _pending(self, key: str) -> None:
        if key in self.state.setdefault("pending", {}):
            message = f"Unresolved Lark operation {key}; no duplicate was created. Reconcile its remote result"
            raise LarkCliError(message, subtype="unresolved_write", uncertain=True)
        self.state["pending"][key] = True
        self.save_state()

    def _done(self, key: str) -> None:
        self.state.setdefault("pending", {}).pop(key, None)
        self.save_state()

    def _schema(self, table: str) -> list[dict]:
        names = {
            "matchups": [
                ("matchup_id", "text"),
                ("run_id", "text"),
                ("case_id", "text"),
                ("task_description", "text"),
                ("category", "text"),
                ("instructions", "text"),
                ("a_images", "attachment"),
                ("b_images", "attachment"),
                ("a_pdf", "attachment"),
                ("b_pdf", "attachment"),
            ],
            "votes": [
                ("matchup_record_id", "text"),
                ("run_id", "text"),
                ("reviewer", "user"),
                ("choice", "text"),
                ("voted_at", "datetime"),
            ],
            "summary": [
                ("summary_id", "text"),
                ("run_id", "text"),
                ("summary", "text"),
            ],
        }
        result = [
            {"name": self.fields[key], "type": field_type}
            for key, field_type in names[table]
        ]
        if table == "votes":
            result[2]["multiple"] = False
        if table == "matchups":
            result.extend(
                {
                    "name": self.copy["choices"][choice],
                    "type": "button",
                    "button_config": {"title": self.copy["choices"][choice]},
                }
                for choice in OUTCOMES
            )
        return result

    def _list(self, command: str, key: str, *args: str) -> list[dict]:
        result = []
        offset = 0
        while True:
            data = self._base(command, *args, "--offset", str(offset), "--limit", "100")
            rows = data.get(key)
            if not isinstance(rows, list):
                message = f"Lark list response omitted {key}"
                raise LarkCliError(message, subtype="invalid_response")
            result.extend(rows)
            total = data.get("total")
            if isinstance(total, int) and len(result) >= total:
                return result
            if len(rows) < 100:
                return result
            offset += len(rows)

    def _ensure_base(self, run_id: str) -> None:
        configured = self.config.get("base_token")
        if configured and configured != self.state.get("base_token"):
            message = "An existing Base must already belong to this run's persisted Feishu state"
            raise ValueError(message)
        if self.state.get("base_token"):
            return
        name = f"{self.config.get('base_name', self.copy['base_name'])} [{_digest(run_id)}]"
        if "base" in self.state.setdefault("pending", {}):
            data = self.cli.run(["base", "+title-resolve", "--title", _digest(run_id)])
            candidates = data.get("candidates", [data])
            matches = [item for item in candidates if item.get("title") == name]
            if len(matches) == 1:
                self.state["base_token"] = _identifier(matches[0], "base_token")
                self.state["url"] = matches[0].get("url")
                self._done("base")
                return
        self._pending("base")
        data = self.cli.run(
            [
                "base",
                "+base-create",
                "--name",
                name,
                "--table-name",
                self.copy["tables"]["matchups"],
                "--time-zone",
                "Asia/Shanghai",
            ],
            payload=self._schema("matchups"),
            payload_flag="--fields",
        )
        base = _object(data.get("base"), "created Base")
        self.state["base_token"] = _identifier(base, "base_token", "app_token")
        self.state["url"] = base.get("url")
        self._done("base")

    def _ensure_tables(self) -> None:
        tables = self._list("+table-list", "tables")
        self.state.setdefault("tables", {})
        self.state.setdefault("fields", {})
        for key in ("matchups", "votes", "summary"):
            name = self.copy["tables"][key]
            matches = [table for table in tables if table.get("name") == name]
            if len(matches) > 1:
                message = "Duplicate arena tables require manual reconciliation"
                raise LarkCliError(message, subtype="duplicate_resource")
            if matches:
                table_id = _identifier(matches[0], "table_id", "id")
            else:
                self._pending(f"table:{key}")
                data = self._base(
                    "+table-create",
                    "--name",
                    name,
                    payload=self._schema(key),
                    payload_flag="--fields",
                )
                table_id = _identifier(
                    _object(data.get("table"), "created table"), "table_id", "id"
                )
            self.state["tables"][key] = table_id
            self._done(f"table:{key}")
            fields = self._list("+field-list", "fields", "--table-id", table_id)
            existing = {field["name"]: field for field in fields}
            for required in self._schema(key):
                actual = existing.get(required["name"], {})
                if actual.get("type") != required["type"]:
                    message = "Arena field schema is incomplete or changed; reconcile before sharing"
                    raise LarkCliError(message, subtype="schema_mismatch")
            self.state["fields"][key] = {
                name: _identifier(field, "field_id", "id")
                for name, field in existing.items()
            }
            self.save_state()
        known_ids = set(self.state["tables"].values())
        if any(
            _identifier(table, "table_id", "id") not in known_ids for table in tables
        ):
            message = "Dedicated arena Base contains unowned tables; refusing to change its sharing policy"
            raise LarkCliError(message, subtype="unowned_resource")

    @staticmethod
    def _contains(actual: object, expected: object) -> bool:
        if isinstance(expected, dict):
            return isinstance(actual, dict) and all(
                (key in actual or value is None)
                and FeishuPublisher._contains(actual.get(key), value)
                for key, value in expected.items()
            )
        if isinstance(expected, list):
            if not expected and actual is None:
                return True
            return (
                isinstance(actual, list)
                and len(actual) == len(expected)
                and all(
                    FeishuPublisher._contains(left, right)
                    for left, right in zip(actual, expected, strict=True)
                )
            )
        return actual == expected

    def _configure_permissions(self) -> None:
        """Use ordinary organization editing on this run's dedicated Base."""
        base = self._base("+base-get").get("base", {})
        if base.get("is_advanced") is True:
            self._base("+advperm-disable", "--yes")
            base = self._base("+base-get").get("base", {})
        if base.get("is_advanced") is not False:
            message = "Lark did not confirm ordinary organization editing; link sharing remains closed"
            raise LarkCliError(message, subtype="permission_verification_failed")
        self.state["permission_mode"] = "organization_editable"
        self.state["permissions_verified"] = True
        self.save_state()

    def _workflow(self, outcome: str) -> dict:
        def value(key: str, text: str, *, reference: bool = False) -> dict:
            return {
                "field_name": self.fields[key],
                "value": [
                    {"value_type": "ref" if reference else "text", "value": text}
                ],
            }

        return {
            "client_token": _digest(f"{self.state['run_id']}:{outcome}"),
            "title": f"{self.copy['workflow_title']} {self.copy['choices'][outcome]}",
            "steps": [
                {
                    "id": "click",
                    "title": self.copy["workflow_trigger_title"],
                    "type": "ButtonTrigger",
                    "next": "save_vote",
                    "data": {
                        "button_type": "buttonField",
                        "table_name": self.copy["tables"]["matchups"],
                    },
                },
                {
                    "id": "save_vote",
                    "title": self.copy["workflow_action_title"],
                    "type": "AddRecordAction",
                    "next": None,
                    "data": {
                        "table_name": self.copy["tables"]["votes"],
                        "field_values": [
                            value(
                                "matchup_record_id", "$.click.recordId", reference=True
                            ),
                            value("reviewer", "$.click.user", reference=True),
                            value("voted_at", "$.click.time", reference=True),
                            value("run_id", self.state["run_id"]),
                            value("choice", outcome),
                        ],
                    },
                },
            ],
        }

    def _ensure_workflows(self) -> None:
        listed = self._base("+workflow-list")
        existing = listed.get("items")
        if existing is None and listed.get("total") == 0:
            existing = []
        if not isinstance(existing, list):
            message = "Lark workflow listing is incomplete; refusing to create duplicate workflows"
            raise LarkCliError(message, subtype="invalid_response")
        workflow_ids = self.state.setdefault("workflow_ids", {})
        for outcome in OUTCOMES:
            body = self._workflow(outcome)
            matches = [
                workflow
                for workflow in existing
                if workflow.get("title") == body["title"]
            ]
            if len(matches) > 1:
                message = "Duplicate arena workflows require reconciliation"
                raise LarkCliError(message, subtype="duplicate_resource")
            if outcome in workflow_ids:
                workflow_id = workflow_ids[outcome]
            elif matches:
                workflow_id = _identifier(matches[0], "workflow_id", "id")
            else:
                self._pending(f"workflow:{outcome}")
                data = self._base("+workflow-create", payload=body)
                workflow_id = _identifier(
                    data.get("workflow", data), "workflow_id", "id"
                )
            workflow_ids[outcome] = workflow_id
            self._done(f"workflow:{outcome}")
            data = self._base("+workflow-get", "--workflow-id", workflow_id)
            actual = data.get("workflow", data)
            if not self._contains(
                actual, {"title": body["title"], "steps": body["steps"]}
            ):
                message = "Workflow readback changed its trigger or vote fields; refusing to enable it"
                raise LarkCliError(message, subtype="workflow_verification_failed")
            field_id = self.state["fields"]["matchups"][self.copy["choices"][outcome]]
            path = f"/open-apis/base/v3/bases/{self.state['base_token']}/tables/{self.state['tables']['matchups']}/fields/{field_id}/button_rule"
            self.cli.run(
                ["api", "PUT", path],
                payload={"workflow_id": workflow_id},
                payload_flag="--data",
            )
            bound = self.cli.run(["api", "GET", path])
            if (
                bound.get("bound") is not True
                or bound.get("target", {}).get("id") != workflow_id
            ):
                message = "Button workflow binding could not be verified"
                raise LarkCliError(message, subtype="workflow_verification_failed")
            self._base("+workflow-enable", "--workflow-id", workflow_id)
            enabled = self._base("+workflow-get", "--workflow-id", workflow_id)
            if enabled.get("workflow", enabled).get("status") != "enabled":
                message = "Lark did not confirm the voting workflow was enabled"
                raise LarkCliError(message, subtype="workflow_verification_failed")

    def _sharing(self, *, open_link: bool) -> None:
        token = self.state["base_token"]
        auth = self.cli.run(
            [
                "drive",
                "permission.members",
                "auth",
                "--token",
                token,
                "--type",
                "bitable",
                "--action",
                "manage_public",
            ]
        )
        if auth.get("auth_result") is not True:
            message = "Current Lark user cannot manage this Base's link permissions"
            raise LarkCliError(message, subtype="authorization")
        current = self.cli.run(
            ["drive", "+permission-get-setting", "--token", token, "--type", "bitable"]
        )
        self.state["public_permission_before"] = current
        self.save_state()
        desired = {
            "external_access": False,
            "invite_external": False,
            "link_share_entity": "tenant_editable" if open_link else "closed",
            "share_entity": "only_full_access",
            "security_entity": "only_full_access",
            "comment_entity": "anyone_can_edit",
        }
        self.cli.run(
            [
                "drive",
                "permission.public",
                "patch",
                "--token",
                token,
                "--type",
                "bitable",
                "--yes",
            ],
            payload=desired,
            payload_flag="--data",
        )
        data = self.cli.run(
            ["drive", "+permission-get-setting", "--token", token, "--type", "bitable"]
        )
        permission = data.get("permission_public", data)
        # CLI 1.0.87 patches Drive v1 but its convenience getter reads v2.
        # v2 separates collaboration management from allowed sharing audiences.
        expected = (
            {
                "external_access_entity": "closed",
                "link_share_entity": desired["link_share_entity"],
                "manage_collaborator_entity": "collaborator_full_access",
                "share_entity": "same_tenant",
                "security_entity": "only_full_access",
                "copy_entity": "only_full_access",
                "comment_entity": desired["comment_entity"],
            }
            if "external_access_entity" in permission
            else desired
        )
        if not self._contains(permission, expected):
            message = "Lark link permission readback differs from the requested organization-only policy"
            raise LarkCliError(message, subtype="permission_verification_failed")
        self.state["shared"] = open_link
        self.save_state()

    def provision(self, run_id: str) -> dict:
        """Build and verify a private Base before enabling organization-only access."""
        if self.state.get("run_id", run_id) != run_id:
            message = "Feishu state belongs to a different arena run"
            raise ValueError(message)
        self.state["run_id"] = run_id
        self.state["permissions_verified"] = False
        self.save_state()
        self._ensure_base(run_id)
        # Closing first also prevents a failed resumed setup from exposing new fields.
        self._sharing(open_link=False)
        self._ensure_tables()
        self._configure_permissions()
        self._ensure_workflows()
        self._sharing(open_link=True)
        return self.state

    def _read_records(
        self, table: str, field_names: Sequence[str], *, machine_id: str | None = None
    ) -> list[dict]:
        args = [
            "base",
            "+record-list",
            "--base-token",
            self.state["base_token"],
            "--table-id",
            self.state["tables"][table],
        ]
        for name in field_names:
            args.extend(["--field-id", name])
        if machine_id is not None:
            key = self.fields["matchup_id" if table == "matchups" else "summary_id"]
            args.extend(
                [
                    "--filter-json",
                    json.dumps(
                        {"logic": "and", "conditions": [[key, "==", machine_id]]}
                    ),
                ]
            )
        return self.cli.records(args)

    def _record(self, table: str, machine_id: str, values: dict) -> str:
        key = f"record:{table}:{machine_id}"
        rows = self._read_records(table, list(values), machine_id=machine_id)
        if len(rows) > 1:
            message = (
                "Duplicate arena machine IDs require reconciliation before writing"
            )
            raise LarkCliError(message, subtype="duplicate_record")
        if rows:
            if rows[0].get(self.fields["run_id"]) != self.state["run_id"]:
                message = "Arena machine ID belongs to a different run; refusing to overwrite it"
                raise LarkCliError(message, subtype="unowned_record")
            record_id = _identifier(rows[0], "record_id")
            self._base(
                "+record-upsert",
                "--table-id",
                self.state["tables"][table],
                "--record-id",
                record_id,
                payload=values,
            )
        else:
            self._pending(key)
            data = self._base(
                "+record-upsert",
                "--table-id",
                self.state["tables"][table],
                payload=values,
            )
            created = data.get("record", {})
            if isinstance(created, dict) and "record_id_list" in created:
                record_ids = created["record_id_list"]
                if not isinstance(record_ids, list) or len(record_ids) != 1:
                    message = "Lark did not confirm one created record ID; reconcile before retrying"
                    raise LarkCliError(
                        message, subtype="invalid_response", uncertain=True
                    )
                record_id = _identifier({"record_id": record_ids[0]}, "record_id")
            else:
                rows = self._read_records(table, list(values), machine_id=machine_id)
                if (
                    len(rows) != 1
                    or rows[0].get(self.fields["run_id"]) != self.state["run_id"]
                ):
                    message = "Lark did not confirm one created record for this run; reconcile before retrying"
                    raise LarkCliError(
                        message, subtype="invalid_response", uncertain=True
                    )
                record_id = _identifier(rows[0], "record_id")
        self.state.setdefault("records", {}).setdefault(table, {})[machine_id] = (
            record_id
        )
        self._done(key)
        return record_id

    def _attachment_rows(self, matchup_id: str, field_name: str) -> list[dict]:
        # The live API can briefly return an old query snapshot after a write.
        # Retry only reads; never repeat the upload to overcome propagation lag.
        for _ in range(3):
            rows = self._read_records(
                "matchups",
                [self.fields["matchup_id"], field_name],
                machine_id=matchup_id,
            )
            if rows:
                break
        if len(rows) != 1:
            message = "Arena matchup disappeared while publishing attachments"
            raise LarkCliError(message, subtype="missing_record")
        items = rows[0].get(field_name) or []
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str)
            for item in items
        ):
            message = "Lark returned malformed attachment metadata"
            raise LarkCliError(message, subtype="invalid_response")
        return items

    def _attachments(
        self, matchup_id: str, record_id: str, side: str, artifact: dict
    ) -> None:
        render = artifact["render"]
        groups = [
            (f"{side}_images", render.get("pages", [])),
            (f"{side}_pdf", [render["pdf"]] if render.get("pdf") else []),
        ]
        for field_key, paths in groups:
            if len(paths) > 50:
                message = "An arena attachment cell cannot contain more than 50 files"
                raise ValueError(message)
            plans = []
            for index, source in enumerate(paths, 1):
                path = Path(source)
                if (
                    not path.is_absolute()
                    or not path.is_file()
                    or path.suffix.lower() not in {".png", ".pdf"}
                ):
                    message = (
                        "Arena artwork must be an existing absolute PNG or PDF path"
                    )
                    raise ValueError(message)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:20]
                neutral = f"{side.upper()}-{index:03d}-{digest}{path.suffix.lower()}"
                plans.append((path, neutral))
            wanted = {name for _, name in plans}
            name = self.fields[field_key]
            current = self._attachment_rows(matchup_id, name)
            stale = [item for item in current if item["name"] not in wanted]
            removal_key = f"attachment-remove:{record_id}:{field_key}"
            if stale:
                if any(
                    not re.fullmatch(
                        rf"{side.upper()}-\d{{3}}-[a-f0-9]{{20}}\.(png|pdf)",
                        item["name"],
                    )
                    for item in stale
                ):
                    message = "Artwork cell contains an unrecognized attachment; reconcile before replacement"
                    raise LarkCliError(message, subtype="unowned_attachment")
                tokens = [_identifier(item, "file_token") for item in stale]
                if removal_key not in self.state.setdefault("pending", {}):
                    self._pending(removal_key)
                # Fresh cell metadata reconciles a lost removal response. Removing
                # these exact old tokens again cannot remove the new revision.
                self._base(
                    "+record-remove-attachment",
                    "--table-id",
                    self.state["tables"]["matchups"],
                    "--record-id",
                    record_id,
                    "--field-id",
                    name,
                    "--yes",
                    *[part for token in tokens for part in ("--file-token", token)],
                )
                for _ in range(3):
                    current = self._attachment_rows(matchup_id, name)
                    if not any(item.get("file_token") in tokens for item in current):
                        break
                if any(item.get("file_token") in tokens for item in current):
                    message = "Lark did not confirm removal of the old artwork revision"
                    raise LarkCliError(
                        message, subtype="invalid_response", uncertain=True
                    )
            self._done(removal_key)
            current_names = {item["name"] for item in current}
            with tempfile.TemporaryDirectory(prefix="arena-artwork-") as directory:
                files = []
                for source, neutral in plans:
                    key = f"attachment:{record_id}:{field_key}:{neutral}"
                    if neutral in current_names:
                        self._done(key)
                        continue
                    self._pending(key)
                    shutil.copyfile(source, Path(directory) / neutral)
                    files.extend(["--file", neutral])
                if files:
                    self._base(
                        "+record-upload-attachment",
                        "--table-id",
                        self.state["tables"]["matchups"],
                        "--record-id",
                        record_id,
                        "--field-id",
                        name,
                        *files,
                        cwd=Path(directory),
                    )
                for _ in range(3):
                    verified = self._attachment_rows(matchup_id, name)
                    uploaded = {item["name"] for item in verified}
                    if uploaded == wanted and len(verified) == len(wanted):
                        break
                if uploaded != wanted or len(verified) != len(wanted):
                    message = "Lark did not confirm exactly the current artwork attachments; reconcile before retrying"
                    raise LarkCliError(
                        message, subtype="invalid_response", uncertain=True
                    )
                # Only retire old upload checkpoints after their record cell has
                # been verified to contain exactly the new complete revision.
                prefix = f"attachment:{record_id}:{field_key}:"
                for key in list(self.state.get("pending", {})):
                    if key.startswith(prefix):
                        self._done(key)

    def publish_matchup(self, matchup: dict, artifact_a: dict, artifact_b: dict) -> str:
        """Upload only explicitly selected public fields and neutral artwork names."""
        if not self.state.get("permissions_verified"):
            message = "Arena permissions must be provisioned before uploading artwork"
            raise LarkCliError(message, subtype="permission_verification_failed")
        for side, artifact in (("a", artifact_a), ("b", artifact_b)):
            if (
                artifact.get("status") != "complete"
                or artifact.get("artifact_id") != matchup[f"{side}_artifact_id"]
                or artifact.get("case_id") != matchup["case_id"]
                or not artifact.get("render", {}).get("pages")
            ):
                message = "Matchup artwork is incomplete or belongs to a different case"
                raise ValueError(message)
        fingerprint = publication_render_fingerprint(artifact_a, artifact_b)
        revisions = self.state.setdefault("publication_render_fingerprints", {})
        changed = revisions.get(matchup["matchup_id"]) != fingerprint
        if changed:
            self.state.setdefault("publication_ready_at", {}).pop(
                matchup["matchup_id"], None
            )
            self.save_state()
        values = {self.fields[key]: matchup[key] for key in ("matchup_id", "case_id")}
        category = matchup.get("category", "text")
        if category not in self.copy["review_tasks"]:
            category = "text"
        values[self.fields["task_description"]] = self.copy["review_tasks"][category]
        values[self.fields["category"]] = self.copy["category_labels"][category]
        values[self.fields["run_id"]] = self.state["run_id"]
        values[self.fields["instructions"]] = self.copy["instructions"]
        record_id = self._record("matchups", matchup["matchup_id"], values)
        self._attachments(matchup["matchup_id"], record_id, "a", artifact_a)
        self._attachments(matchup["matchup_id"], record_id, "b", artifact_b)
        revisions[matchup["matchup_id"]] = fingerprint
        self.state.setdefault("publication_ready_at", {}).setdefault(
            matchup["matchup_id"], utc_now()
        )
        self.save_state()
        return record_id

    def get_publication_ready_at(self, matchup_id: str) -> str | None:
        """Return the first time both sides' complete attachments were verified."""
        value = self.state.get("publication_ready_at", {}).get(matchup_id)
        return value if isinstance(value, str) else None

    def fetch_votes(self) -> list[dict]:
        """Return each native click independently; aggregation decides deduplication."""
        names = ["matchup_record_id", "run_id", "reviewer", "choice", "voted_at"]
        rows = self._read_records("votes", [self.fields[key] for key in names])
        matchup_ids = {
            record_id: matchup_id
            for matchup_id, record_id in self.state.get("records", {})
            .get("matchups", {})
            .items()
        }
        result = []
        for row in rows:
            reviewers = row.get(self.fields["reviewer"]) or []
            reviewer_id = reviewers[0].get("id") if len(reviewers) == 1 else None
            matchup_record_id = row.get(self.fields["matchup_record_id"])
            try:
                timestamp = datetime.fromisoformat(
                    str(row.get(self.fields["voted_at"]))
                )
                created_at = (
                    timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
                    if timestamp.tzinfo
                    else None
                )
            except ValueError:
                created_at = None
            result.append(
                {
                    "vote_id": row["record_id"],
                    "run_id": row.get(self.fields["run_id"]),
                    "matchup_id": matchup_ids.get(matchup_record_id),
                    "matchup_record_id": matchup_record_id,
                    "reviewer_id": reviewer_id,
                    "choice": row.get(self.fields["choice"]),
                    "created_at": created_at,
                }
            )
        return result

    def publish_summary(self, summary: dict) -> None:
        """Store model aggregates without prompts or matchup-to-model mappings."""
        # This explicit aggregate allowlist also rejects accidental prompt-bearing manifests.
        allowed = {
            "schema_version",
            "run_id",
            "valid_vote_count",
            "rejected_vote_count",
        }
        safe = {key: value for key, value in summary.items() if key in allowed}
        model_keys = {
            "model",
            "requested",
            "wins",
            "losses",
            "ties",
            "both_bad",
            "valid_votes",
            "generated",
            "failed",
            "win_rate",
            "both_bad_rate",
            "covered_cases",
            "failure_rate",
            "render_failed",
            "truncated",
            "input_mismatch",
        }
        safe["models"] = [
            {key: value for key, value in model.items() if key in model_keys}
            for model in summary.get("models", [])
        ]
        machine_id = f"summary:{self.state['run_id']}"
        values = {
            self.fields["summary_id"]: machine_id,
            self.fields["run_id"]: self.state["run_id"],
            self.fields["summary"]: json.dumps(
                safe, ensure_ascii=False, sort_keys=True
            ),
        }
        self._record("summary", machine_id, values)
