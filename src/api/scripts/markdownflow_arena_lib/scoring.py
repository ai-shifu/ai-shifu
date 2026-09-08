"""Count auditable first votes without modifying the raw Feishu records."""

from __future__ import annotations

from datetime import UTC, datetime

from .state import ArenaError, publication_render_fingerprint


def _timestamp(value: object) -> datetime | None:
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, UTC)
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _has_current_publication(pair: dict | None, artifacts: dict) -> bool:
    if pair is None:
        return False
    try:
        current = publication_render_fingerprint(
            artifacts[pair["a_artifact_id"]], artifacts[pair["b_artifact_id"]]
        )
    except (ArenaError, KeyError, TypeError):
        return False
    return pair.get("publication_render_fingerprint") == current


def summarize_votes(manifest: dict, votes: list[dict]) -> dict:
    """Score only authenticated, valid, completed comparisons once per reviewer."""
    artifacts = manifest["artifacts"]
    pairs = {pair["matchup_id"]: pair for pair in manifest["matchups"]}
    remote_ids = {
        pair["record_id"]: pair for pair in pairs.values() if pair.get("record_id")
    }
    models = {
        entry["model"]: {
            "model": entry["model"],
            "requested": entry["requested"],
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "both_bad": 0,
            "valid_votes": 0,
            "case_ids": set(),
            "generated": 0,
            "failed": 0,
            "render_failed": 0,
            "truncated": 0,
            "input_mismatch": 0,
        }
        for entry in manifest["models"]
    }
    for artifact in artifacts.values():
        model = models[artifact["model"]["model"]]
        model["generated"] += artifact.get("generation_status") == "complete"
        model["failed"] += artifact.get("status") in {
            "generation_failed",
            "generation_unknown",
            "truncated",
        }
        for key in ("render_failed", "truncated", "input_mismatch"):
            model[key] += artifact.get("status") == key
    rejected = []
    ordered = []
    for vote in votes:
        timestamp = _timestamp(vote.get("created_at"))
        actor = vote.get("reviewer_id")
        pair = remote_ids.get(vote.get("matchup_record_id"))
        published_at = _timestamp(pair.get("published_at")) if pair else None
        valid_pair = (
            pair is not None
            and _has_current_publication(pair, artifacts)
            and published_at is not None
            and timestamp is not None
            and timestamp >= published_at
            and vote.get("matchup_id", pair["matchup_id"]) == pair["matchup_id"]
            and all(
                artifacts.get(pair[key], {}).get("status") == "complete"
                for key in ("a_artifact_id", "b_artifact_id")
            )
        )
        if (
            not timestamp
            or not isinstance(actor, str)
            or not actor.strip()
            or not valid_pair
            or vote.get("choice") not in {"a", "b", "tie", "both_bad"}
            or vote.get("run_id", manifest["run_id"]) != manifest["run_id"]
        ):
            rejected.append({"vote_id": vote.get("vote_id"), "reason": "invalid"})
            continue
        ordered.append((timestamp, str(vote.get("vote_id", "")), actor, pair, vote))
    ordered.sort(key=lambda item: (item[0], item[1]))
    seen = set()
    outcomes = []
    for _, vote_id, actor, pair, vote in ordered:
        key = (pair["matchup_id"], actor)
        if key in seen:
            rejected.append({"vote_id": vote_id, "reason": "duplicate"})
            continue
        seen.add(key)
        choice = vote["choice"]
        for side in ("a", "b"):
            artifact = artifacts[pair[f"{side}_artifact_id"]]
            model = models[artifact["model"]["model"]]
            outcome = (
                "ties"
                if choice == "tie"
                else "both_bad"
                if choice == "both_bad"
                else "wins"
                if choice == side
                else "losses"
            )
            model[outcome] += 1
            model["valid_votes"] += 1
            model["case_ids"].add(pair["case_id"])
        outcomes.append(
            {"vote_id": vote_id, "matchup_id": pair["matchup_id"], "choice": choice}
        )
    rows = []
    for model in models.values():
        denominator = model["wins"] + model["losses"] + model["ties"]
        model["win_rate"] = (
            (model["wins"] + 0.5 * model["ties"]) / denominator if denominator else None
        )
        model["both_bad_rate"] = (
            model["both_bad"] / model["valid_votes"] if model["valid_votes"] else None
        )
        model["covered_cases"] = len(model.pop("case_ids"))
        total = model["generated"] + model["failed"]
        model["failure_rate"] = model["failed"] / total if total else None
        rows.append(model)
    return {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "valid_vote_count": len(outcomes),
        "rejected_vote_count": len(rejected),
        "models": rows,
        "accepted_votes": outcomes,
        "rejected_votes": rejected,
    }
