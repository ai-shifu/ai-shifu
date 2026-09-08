#!/usr/bin/env python3
"""Generate published-course model comparisons and collect Feishu blind votes."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from markdownflow_arena_lib.state import (  # noqa: E402
    SCHEMA_VERSION,
    ArenaError,
    read_json,
    run_lock,
    utc_now,
    validate_config,
    write_json,
)

DEFAULT_RUN_ROOT = API_ROOT.parents[1] / "artifacts/runs/markdownflow-arena"


def parser() -> argparse.ArgumentParser:
    """Describe the private operator commands."""
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="Run a new batch or resume its frozen manifest"
    )
    selection = run.add_mutually_exclusive_group(required=True)
    selection.add_argument("--config", type=Path)
    selection.add_argument("--resume", type=Path, metavar="RUN_DIRECTORY")
    run.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    run.add_argument("--smoke-only", action="store_true")
    run.add_argument(
        "--retry-failed",
        action="store_true",
        help="Explicitly retry failed or uncertain paid requests",
    )
    summary = commands.add_parser("summarize", help="Recompute first-vote statistics")
    summary.add_argument("--run-id", required=True)
    summary.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    commands.add_parser("worker", help=argparse.SUPPRESS)
    return root


def _resume_directory(args: argparse.Namespace) -> Path:
    """Resolve a manifest directory without accepting a path as a run ID."""
    if args.command == "summarize":
        if Path(args.run_id).name != args.run_id:
            message = "run-id must be a manifest ID, not a path"
            raise ArenaError(message)
        return args.run_root.resolve() / args.run_id
    return args.resume.resolve()


def _load_manifest(run_dir: Path) -> dict:
    """Reject a manifest whose schema cannot safely be resumed."""
    manifest = read_json(run_dir / "manifest.json")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        message = "Unsupported manifest schema version"
        raise ArenaError(message)
    return manifest


def main() -> int:
    """Persist progress even when a later external stage fails."""
    args = parser().parse_args()
    if args.command == "worker":
        from markdownflow_arena_lib.worker import worker_main

        return worker_main()
    run_dir = None
    try:
        if args.command == "run" and args.config:
            config = validate_config(read_json(args.config.resolve()))
            run_id = "arena_" + uuid.uuid4().hex
            run_dir = args.run_root.resolve() / run_id
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "created_at": utc_now(),
                "status": "created",
                "config": config,
                "cases": [],
                "models": [],
                "artifacts": {},
                "matchups": [],
                "feishu": {},
            }
        else:
            run_dir = _resume_directory(args)
            manifest = _load_manifest(run_dir)
            config = validate_config(manifest["config"])
        with run_lock(run_dir):
            # Re-read after locking so another completed operation is not lost.
            manifest_path = run_dir / "manifest.json"
            if manifest_path.exists():
                manifest = _load_manifest(run_dir)

            def save() -> None:
                write_json(manifest_path, manifest)

            save()
            from markdownflow_arena_lib.feishu import FeishuPublisher
            from markdownflow_arena_lib.pipeline import (
                ArenaPipeline,
                BrowserRenderer,
                WorkerBackend,
            )

            publisher = FeishuPublisher(config["feishu"], manifest["feishu"], save)
            pipeline = ArenaPipeline(
                manifest,
                run_dir,
                WorkerBackend(config, run_dir),
                BrowserRenderer(config),
                publisher,
                save,
            )
            try:
                summary = (
                    pipeline.summary()
                    if args.command == "summarize"
                    else pipeline.run(
                        smoke_only=args.smoke_only,
                        retry_failed=args.retry_failed,
                    )
                )
            except Exception:
                manifest["last_failure_at"] = utc_now()
                save()
                raise
            print(
                json.dumps(
                    {
                        "ok": True,
                        "run_id": manifest["run_id"],
                        "status": manifest["status"],
                        "run_directory": str(run_dir),
                        "valid_votes": summary["valid_vote_count"],
                        "published_matchups": sum(
                            bool(item.get("record_id")) for item in manifest["matchups"]
                        ),
                        "feishu": {
                            key: value
                            for key, value in manifest["feishu"].items()
                            if key.endswith("url")
                        },
                    },
                    ensure_ascii=False,
                )
            )
    except ArenaError as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(error),
                    "run_directory": str(run_dir) if run_dir else None,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(error).__name__,
                    "error": "Arena operation failed; inspect the private run manifest",
                    "run_directory": str(run_dir) if run_dir else None,
                }
            ),
            file=sys.stderr,
        )
        return 1
    else:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
