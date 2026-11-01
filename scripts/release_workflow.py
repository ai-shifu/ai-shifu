# ruff: noqa: INP001 -- Standalone repository release CLI.
"""Validate, stage and publish exact-source product releases without merging."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

PACKAGES = ("src/web",)
PRIMARY = "src/web/package.json"
ENGINE = "src/api/markdownflow/engine/__init__.py"
VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
IMAGE_PATTERN = re.compile(
    r"(?m)^(\s*image:\s*)aishifu/(ai-shifu-api|ai-shifu-web|ai-shifu-cook-web):([^\s#]+)"
)
ENGINE_PATTERN = re.compile(r"(?m)^(__version__\s*=\s*)(['\"])([^'\"]+)\2")
IMAGES_MARKER = "<!-- ai-shifu-release-images-verified:"


def git(*arguments: str) -> str:
    """Run local Git with explicit arguments; never invoke a shell."""
    return subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def version_tuple(version: str) -> tuple[int, ...]:
    """Accept canonical final product versions only."""
    if not VERSION_PATTERN.fullmatch(version):
        message = f"Invalid final release version: {version!r}"
        raise ValueError(message)
    return tuple(map(int, version.split(".")))


def source_commit(source: str) -> str:
    """Require an exact commit object, not a branch or tag or option."""
    if not SHA_PATTERN.fullmatch(source):
        message = "A full lowercase source commit SHA is required"
        raise ValueError(message)
    if git("rev-parse", f"{source}^{{commit}}") != source:
        message = "Source must identify a commit directly"
        raise ValueError(message)
    return source


def compose_paths() -> list[str]:
    """Discover tracked Compose bundles, excluding the rolling latest contract."""
    return [
        path
        for path in git(
            "ls-files", "*docker-compose*.yml", "*docker-compose*.yaml"
        ).splitlines()
        if not Path(path).name.startswith("docker-compose.latest.")
    ]


def prepare(tag: str, source: str) -> None:
    """Update only the repository's owned version fields for the version PR."""
    version = tag.removeprefix("v")
    if tag != f"v{version}":
        message = "Release tag must start with v"
        raise ValueError(message)
    requested = version_tuple(version)
    source_commit(source)
    if git("rev-parse", "HEAD") != source:
        message = "Preparation checkout must match the frozen source"
        raise ValueError(message)
    current = json.loads(git("show", f"{source}:{PRIMARY}"))["version"]
    if requested <= version_tuple(current):
        message = "The release version must increase"
        raise ValueError(message)
    if tag in git("tag", "--list").splitlines():
        message = f"Release tag already exists: {tag}"
        raise ValueError(message)

    for package in PACKAGES:
        for filename in ("package.json", "package-lock.json"):
            path = Path(package, filename)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["version"] = version
            if filename == "package-lock.json" and "" in data.get("packages", {}):
                data["packages"][""]["version"] = version
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    engine = Path(ENGINE)
    engine.write_text(
        ENGINE_PATTERN.sub(
            lambda match: f"{match[1]}{match[2]}{version}{match[2]}",
            engine.read_text(encoding="utf-8"),
        ),
        encoding="utf-8",
    )
    for name in compose_paths():
        path = Path(name)
        path.write_text(
            IMAGE_PATTERN.sub(
                lambda match: (
                    f"{match[1]}aishifu/{'ai-shifu-web' if match[2] == 'ai-shifu-cook-web' else match[2]}:{tag}"
                ),
                path.read_text(encoding="utf-8"),
            ),
            encoding="utf-8",
        )


def version_at(source: str) -> str:
    """Read the primary release version at the exact Git object."""
    version = json.loads(git("show", f"{source}:{PRIMARY}"))["version"]
    version_tuple(version)
    return version


def previous_tag(source: str, version: str) -> str:
    """Select the highest final version tag reachable from the frozen candidate."""
    eligible = [
        tag
        for tag in git("tag", "--merged", source).splitlines()
        if tag.startswith("v")
        and VERSION_PATTERN.fullmatch(tag[1:])
        and version_tuple(tag[1:]) < version_tuple(version)
    ]
    return max(eligible, key=lambda tag: version_tuple(tag[1:]), default="")


def validate_versions(source: str, version: str) -> None:
    """Require npm manifests/lock roots, engine and first-party bundles to agree."""
    for package in PACKAGES:
        for filename in ("package.json", "package-lock.json"):
            path = f"{package}/{filename}"
            data = json.loads(git("show", f"{source}:{path}"))
            values = [data.get("version")]
            if filename == "package-lock.json" and "packages" in data:
                values.append(data["packages"].get("", {}).get("version"))
            if any(value != version for value in values):
                message = f"Source version mismatch in {path}"
                raise ValueError(message)
    engine = ENGINE_PATTERN.findall(git("show", f"{source}:{ENGINE}"))
    if len(engine) != 1 or engine[0][2] != version:
        message = "Source engine version mismatch"
        raise ValueError(message)
    for path in git("ls-tree", "-r", "--name-only", source).splitlines():
        if not re.fullmatch(r"docker-compose.*\.ya?ml", Path(path).name):
            continue
        images = IMAGE_PATTERN.findall(git("show", f"{source}:{path}"))
        expected = (
            "latest"
            if Path(path).name.startswith("docker-compose.latest.")
            else f"v{version}"
        )
        if any(
            name == "ai-shifu-cook-web" or tag != expected for _, name, tag in images
        ):
            message = f"Source Compose image/version mismatch in {path}"
            raise ValueError(message)
        if path == "docker/docker-compose.yml" and not {
            "ai-shifu-api",
            "ai-shifu-web",
        }.issubset({name for _, name, _ in images}):
            message = "Pinned release bundle must contain both first-party images"
            raise ValueError(message)


def detect(source: str, event: dict) -> dict[str, str]:
    """Freeze a main-push candidate or explicitly recover its original commit."""
    source_commit(source)
    recovery = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if recovery:
        inputs = event.get("inputs") or {}
        if (
            os.environ.get("GITHUB_REF") != "refs/heads/main"
            or inputs.get("source_commit") != source
            or inputs.get("expected_version") != version_at(source)
        ):
            message = "Recovery requires main, the original full source SHA and matching expected version"
            raise ValueError(message)
    elif (
        os.environ.get("GITHUB_EVENT_NAME") != "push"
        or event.get("ref") != "refs/heads/main"
        or event.get("after") != source
        or event.get("forced")
        or event.get("deleted")
    ):
        message = "Draft detection requires the exact main push event commit"
        raise ValueError(message)
    git("merge-base", "--is-ancestor", source, "refs/remotes/origin/main")
    version = version_at(source)
    values = {
        "create_draft": "false",
        "commit": source,
        "version": version,
        "tag": f"v{version}",
        "previous_tag": previous_tag(source, version),
    }
    if recovery:
        validate_versions(source, version)
        values["create_draft"] = "true"
        return values
    if event.get("before") == "0" * 40:
        return values
    before = source_commit(event["before"])
    git("merge-base", "--is-ancestor", before, source)
    if PRIMARY not in git("ls-tree", "--name-only", before, "--", PRIMARY).splitlines():
        return values
    previous = version_at(before)
    if version_tuple(version) < version_tuple(previous):
        message = "The release version must increase, not decrease"
        raise ValueError(message)
    if version != previous:
        validate_versions(source, version)
    values["create_draft"] = str(version != previous).lower()
    return values


def github(
    method: str, path: str, payload: dict | None = None, *, missing_ok: bool = False
) -> object:
    """Use authenticated JSON REST requests; only explicit optional 404s are absent."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        message = "GH_TOKEN is required for release API access"
        raise ValueError(message)
    request = urllib.request.Request(
        f"https://api.github.com/{path}",
        method=method,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 -- The URL always starts with the fixed GitHub HTTPS API host.
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise


def validate_provenance(source: str, version: str, repository: str) -> int:
    """Require an exact merged release PR and reject observable automation evidence.

    A GitHub User is not an attestation of a human. Recorded auto-merge may be
    cleared after merge; repository policy and manual review remain essential.
    """
    source_commit(source)
    git("merge-base", "--is-ancestor", source, "refs/remotes/origin/main")
    if version_tuple(version_at(git("rev-parse", f"{source}^1"))) >= version_tuple(
        version
    ):
        message = "The merged source commit must introduce the version increase"
        raise ValueError(message)
    candidates = []
    page = 1
    while True:
        pulls = github(
            "GET", f"repos/{repository}/commits/{source}/pulls?per_page=100&page={page}"
        )
        if not isinstance(pulls, list):
            message = "Expected a list of associated pull requests"
            raise TypeError(message)
        candidates.extend(pulls)
        if len(pulls) < 100:
            break
        page += 1
    matches = []
    for candidate in candidates:
        number = candidate.get("number")
        if not isinstance(number, int) or number <= 0:
            message = "Invalid associated pull request number"
            raise ValueError(message)
        pr = github("GET", f"repos/{repository}/pulls/{number}")
        base, head = pr.get("base") or {}, pr.get("head") or {}
        merger = pr.get("merged_by") or {}
        login = str(merger.get("login") or "").lower()
        if (
            pr.get("merged") is True
            and pr.get("state") == "closed"
            and pr.get("merged_at")
            and pr.get("merge_commit_sha") == source
            and pr.get("auto_merge") is None
            and base.get("ref") == "main"
            and (base.get("repo") or {}).get("full_name") == repository
            and head.get("ref") == f"release/version-bump-v{version}"
            and (head.get("repo") or {}).get("full_name") == repository
            and merger.get("type") == "User"
            and login
            and login not in {"ai-shifu-bot", "github-actions"}
            and not login.endswith("[bot]")
        ):
            matches.append(number)
    if len(matches) != 1:
        message = "Require one exact merged-to-main release PR with a non-automation merger and no recorded auto-merge"
        raise ValueError(message)
    return matches[0]


def remote_tag(repository: str, tag: str) -> str | None:
    """Peel lightweight or annotated version tags without ever moving them."""
    record = github("GET", f"repos/{repository}/git/ref/tags/{tag}", missing_ok=True)
    if record is None:
        return None
    target = record["object"]
    seen = set()
    while target.get("type") == "tag":
        sha = target.get("sha", "")
        if not SHA_PATTERN.fullmatch(str(sha)) or sha in seen:
            message = "Invalid or cyclic annotated tag object"
            raise ValueError(message)
        seen.add(sha)
        target = github("GET", f"repos/{repository}/git/tags/{sha}")["object"]
    if target.get("type") != "commit" or not SHA_PATTERN.fullmatch(
        str(target.get("sha", ""))
    ):
        message = "Formal tag must resolve to an exact commit"
        raise ValueError(message)
    return target["sha"]


def find_release(repository: str, tag: str) -> dict | None:
    """List authenticated releases, including drafts, without trusting a tag-only 404."""
    matches = []
    page = 1
    while True:
        records = github("GET", f"repos/{repository}/releases?per_page=100&page={page}")
        if not isinstance(records, list):
            message = "Expected a release list including drafts"
            raise TypeError(message)
        matches.extend(record for record in records if record.get("tag_name") == tag)
        if len(records) < 100:
            break
        page += 1
    if len(matches) > 1:
        message = "Multiple releases claim the same formal tag"
        raise ValueError(message)
    return matches[0] if matches else None


def validate_record(record: dict, source: str, version: str, *, draft: bool) -> None:
    """Fail closed on mismatched release identity, target or publication state."""
    marker = f"<!-- ai-shifu-release-source:{source} -->"
    body = record.get("body") or ""
    if (
        record.get("tag_name") != f"v{version}"
        or record.get("target_commitish") != source
        or record.get("name") != f"Release v{version}"
        or record.get("draft") is not draft
        or record.get("prerelease") is not False
        or body.count("<!-- ai-shifu-release-source:") != 1
        or marker not in body
    ):
        message = "Release tag, source, version or draft/public state mismatch"
        raise ValueError(message)


def images_verified(record: dict, source: str) -> bool:
    """Read the coordinator's source-specific completion marker, not an attestation."""
    body = record.get("body") or ""
    count = body.count(IMAGES_MARKER)
    if not count:
        return False
    if count != 1 or f"{IMAGES_MARKER}{source} -->" not in body:
        message = "Release image completion marker differs from the verified source"
        raise ValueError(message)
    return True


def create_draft(
    source: str,
    event: dict,
    repository: str,
    notes: str,
    *,
    resume_published: bool = False,
) -> str:
    """Pin an exact-source draft; optionally resume an owned public release read-only."""
    values = detect(source, event)
    if values["create_draft"] != "true":
        message = "Draft creation requires a main version increase"
        raise ValueError(message)
    version, tag = values["version"], values["tag"]
    if "<!-- ai-shifu-release-source:" in notes or IMAGES_MARKER in notes:
        message = "Release notes must not contain reserved source or image markers"
        raise ValueError(message)
    validate_provenance(source, version, repository)
    existing = find_release(repository, tag)
    if existing is not None:
        public_retry = resume_published and existing.get("draft") is False
        validate_record(existing, source, version, draft=not public_retry)
        completed = images_verified(existing, source)
        if public_retry and not completed:
            message = "Published recovery requires the original verified-image marker"
            raise ValueError(message)
    tagged = remote_tag(repository, tag)
    if tagged is not None and tagged != source:
        message = "Conflicting formal version tag; refusing to move it"
        raise ValueError(message)
    if existing is not None and existing.get("draft") is False and tagged is None:
        message = "Published recovery requires the existing exact-source formal tag"
        raise ValueError(message)
    if tagged is None:
        github(
            "POST",
            f"repos/{repository}/git/refs",
            {"ref": f"refs/tags/{tag}", "sha": source},
        )
        if remote_tag(repository, tag) != source:
            message = "Formal tag readback differs from the source"
            raise ValueError(message)
    expected_body = (
        existing["body"]
        if existing is not None
        else f"<!-- ai-shifu-release-source:{source} -->\n\n{notes}"
    )
    if existing is None:
        existing = github(
            "POST",
            f"repos/{repository}/releases",
            {
                "tag_name": tag,
                "target_commitish": source,
                "name": f"Release {tag}",
                "body": expected_body,
                "draft": True,
                "prerelease": False,
                "make_latest": "false",
                "generate_release_notes": False,
            },
        )
    final = github("GET", f"repos/{repository}/releases/{existing['id']}")
    validate_record(final, source, version, draft=existing["draft"])
    completed = images_verified(final, source)
    if not final["draft"] and not completed:
        message = "Published recovery lost the verified-image marker"
        raise ValueError(message)
    if final.get("body") != expected_body:
        message = "Draft release notes readback differs from the expected body"
        raise ValueError(message)
    if remote_tag(repository, tag) != source:
        message = "Final formal tag differs from the verified source"
        raise ValueError(message)
    return final["html_url"]


def validate_candidate(source: str, tag: str, repository: str) -> dict[str, str]:
    """Validate a trusted draft before images, or an owned completed retry."""
    source_commit(source)
    version = tag.removeprefix("v")
    if tag != f"v{version}":
        message = "Formal release tags must start with v"
        raise ValueError(message)
    version_tuple(version)
    if version_at(source) != version:
        message = "Release tag and source version differ"
        raise ValueError(message)
    validate_versions(source, version)
    validate_provenance(source, version, repository)
    record = find_release(repository, tag)
    if record is None:
        message = "The exact-source Release draft must exist before image publication"
        raise ValueError(message)
    draft = record.get("draft")
    if not isinstance(draft, bool):
        message = "Release draft state must be explicit"
        raise TypeError(message)
    validate_record(record, source, version, draft=draft)
    final = github("GET", f"repos/{repository}/releases/{record['id']}")
    validate_record(final, source, version, draft=draft)
    completed = images_verified(final, source)
    if not draft and not completed:
        message = "Published recovery requires the original verified-image marker"
        raise ValueError(message)
    if remote_tag(repository, tag) != source:
        message = "Formal tag differs from the verified release source"
        raise ValueError(message)
    return {
        "should_build": str(draft).lower(),
        "is_prerelease": "false",
        "tag": tag,
        "version": version,
        "commit": source,
        "url": final["html_url"],
    }


def publish_release(source: str, tag: str, repository: str) -> str:
    """Publish after the caller's image gate, preserving notes and completed retries."""
    values = validate_candidate(source, tag, repository)
    if values["should_build"] == "false":
        return values["url"]
    record = find_release(repository, tag)
    if record is None:
        message = "Release disappeared before publication"
        raise ValueError(message)
    version = values["version"]
    validate_record(record, source, version, draft=True)
    body = record["body"]
    if not images_verified(record, source):
        body = body.rstrip() + f"\n\n{IMAGES_MARKER}{source} -->\n"
    github(
        "PATCH",
        f"repos/{repository}/releases/{record['id']}",
        {
            "draft": False,
            "prerelease": False,
            "body": body,
            "make_latest": "legacy",
        },
    )
    final = github("GET", f"repos/{repository}/releases/{record['id']}")
    validate_record(final, source, version, draft=False)
    if final.get("body") != body or not images_verified(final, source):
        message = "Published release notes or image marker readback differs"
        raise ValueError(message)
    if remote_tag(repository, tag) != source:
        message = "Published formal tag differs from the verified source"
        raise ValueError(message)
    return final["html_url"]


def validate_published(source: str, event: dict, repository: str) -> dict[str, str]:
    """Validate publication identity before the reusable image builder can run."""
    if event.get("action") != "published":
        message = "Release image validation requires a published event"
        raise ValueError(message)
    record = event["release"]
    if record.get("draft") is True or record.get("prerelease") is True:
        return {
            "should_build": "false",
            "is_prerelease": str(record.get("prerelease") is True).lower(),
        }
    source_commit(source)
    tag = record["tag_name"]
    version = tag.removeprefix("v")
    if tag != f"v{version}":
        message = "Formal release tags must start with v"
        raise ValueError(message)
    version_tuple(version)
    if version_at(source) != version:
        message = "Published release tag and source version differ"
        raise ValueError(message)
    validate_versions(source, version)
    validate_record(record, source, version, draft=False)
    validate_provenance(source, version, repository)
    final = github("GET", f"repos/{repository}/releases/{record['id']}")
    validate_record(final, source, version, draft=False)
    if remote_tag(repository, tag) != source:
        message = "Published formal tag differs from the verified source"
        raise ValueError(message)
    return {
        "should_build": str(not images_verified(final, source)).lower(),
        "is_prerelease": "false",
        "tag": tag,
        "version": version,
        "commit": source,
    }


def main() -> None:
    """Expose frozen-source release operations; never merge a version PR."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--tag", required=True)
    preparation.add_argument("--source", required=True)
    detection = commands.add_parser("detect")
    detection.add_argument("--source", required=True)
    detection.add_argument("--event", required=True, type=Path)
    detection.add_argument("--output", required=True, type=Path)
    for name in (
        "draft",
        "stage",
        "validate-published",
        "validate-candidate",
        "publish",
    ):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True)
        if name in {"draft", "stage", "validate-published"}:
            command.add_argument("--event", required=True, type=Path)
        else:
            command.add_argument("--tag", required=True)
        command.add_argument("--repository", required=True)
        command.add_argument("--output", required=True, type=Path)
        if name in {"draft", "stage"}:
            command.add_argument("--notes", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.tag, args.source)
            return
        event = (
            json.loads(args.event.read_text(encoding="utf-8"))
            if hasattr(args, "event")
            else None
        )
        if args.command == "detect":
            values = detect(args.source, event)
        else:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
                parser.error("Repository must be owner/name")
            if args.command in {"draft", "stage"}:
                values = {
                    "url": create_draft(
                        args.source,
                        event,
                        args.repository,
                        args.notes.read_text(encoding="utf-8"),
                        resume_published=args.command == "stage",
                    )
                }
                if args.command == "stage":
                    values.update(
                        validate_candidate(
                            args.source,
                            f"v{version_at(args.source)}",
                            args.repository,
                        )
                    )
            elif args.command == "validate-candidate":
                values = validate_candidate(args.source, args.tag, args.repository)
            elif args.command == "publish":
                values = {
                    "url": publish_release(args.source, args.tag, args.repository),
                    "published": "true",
                }
            else:
                if os.environ.get("GITHUB_EVENT_NAME") != "release":
                    parser.error("Published validation requires a release event")
                values = validate_published(args.source, event, args.repository)
        if any("\n" in value or "\r" in value for value in values.values()):
            parser.error("Release outputs must be single-line validated values")
        with args.output.open("a", encoding="utf-8") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(1, f"Release guard: {error}\n")


if __name__ == "__main__":
    main()
