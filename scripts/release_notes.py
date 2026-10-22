# ruff: noqa: INP001 -- Standalone repository release notes CLI.
"""Generate product release notes at an explicit, frozen Git commit."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from release_workflow import git, github, previous_tag, source_commit, version_tuple


def normalize_changelog(raw: str) -> str:
    """Retain the preparation workflow's Commitizen heading normalization."""
    lines = []
    for raw_line in raw.splitlines():
        line = raw_line
        if re.match(r"^##\s*\[?Unreleased\]?\s*$", line.strip()):
            continue
        line = re.sub(r"^###\s+Feat\b.*$", "### New Feature", line, flags=re.IGNORECASE)
        line = re.sub(
            r"^###\s+Fix(?:es)?\b.*$", "### Bug Fixes", line, flags=re.IGNORECASE
        )
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip("\n"))


def annotate_product_authors(content: str, repository: str) -> str:
    """Enrich PR references best-effort without interpreting notes as shell text."""
    authors = {}
    for number in sorted({int(value) for value in re.findall(r"\(#(\d+)\)", content)}):
        try:
            record = github("GET", f"repos/{repository}/pulls/{number}")
            login = (record.get("user") or {}).get("login") or ""
        except Exception:
            login = ""
        authors[number] = f"@{login}" if login else ""
    lines = []
    for line in content.splitlines():

        def annotate(match: re.Match[str], line: str = line) -> str:
            suffix = line[match.end() :]
            if re.match(r"\s*\(@", suffix) or re.match(r"\s+by\s+@", suffix):
                return match[0]
            author = authors[int(match[1])]
            return f"{match[0]} ({author})" if author else match[0]

        lines.append(re.sub(r"\(#(\d+)\)", annotate, line))
    return "\n".join(lines)


def commitizen_notes(source: str, previous: str) -> str:
    """Render at an isolated frozen checkout using Commitizen's revision option."""
    # Commitizen's positional range accepts versions, not arbitrary Git SHAs.
    # Its --start-rev ends at HEAD, so isolate both HEAD and config at the source.
    repository = git("rev-parse", "--show-toplevel")
    with tempfile.TemporaryDirectory(prefix="ai-shifu-release-notes-") as directory:
        subprocess.run(
            [
                "git",
                "clone",
                "--shared",
                "--no-checkout",
                "--quiet",
                "--",
                repository,
                directory,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "checkout", "--detach", "--quiet", source, "--"],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["cz", "changelog", "--dry-run", "--start-rev", previous],
            cwd=directory,
            check=False,
            capture_output=True,
            text=True,
        )
    return normalize_changelog(result.stdout) if result.returncode == 0 else ""


def product_notes(source: str, previous: str, repository: str) -> str:
    """Use Commitizen first, retaining every Git subject/PR omitted by its filters."""
    if not previous:
        about = "This project follows semantic versioning and conventional commits for reliable releases."
        try:
            readme = git("show", f"{source}:README.md")
        except subprocess.CalledProcessError:
            readme = ""
        description = [
            line
            for line in readme.splitlines()[1:10]
            if line.strip() and not line.startswith("#")
        ]
        if description:
            about = " ".join(description[:3])
        introduction = f"## Initial Release\n\nThis is the first tagged release of **{repository.rsplit('/', maxsplit=1)[-1]}**.\n\n## About\n\n{about}"
        for section in (
            "Features",
            "Installation",
            "Usage",
            "Getting Started",
            "Quick Start",
        ):
            match = re.search(rf"(?ms)^# {re.escape(section)}\n.*?(?=^# |\Z)", readme)
            if match:
                return introduction + "\n\n" + match[0].strip()
        return (
            introduction
            + "\n\n## Getting Started\n\nPlease check the README.md file for installation and usage instructions."
        )
    revision_range = f"{previous}..{source}"
    subjects = git("log", "--pretty=format:%s", revision_range, "--").splitlines()
    try:
        content = commitizen_notes(source, previous)
    except (OSError, subprocess.CalledProcessError):
        content = ""
    if not content:
        sections: dict[str, list[str]] = {}
        headings = {
            "feat": "New Feature",
            "fix": "Bug Fixes",
            "refactor": "Code Refactoring",
            "docs": "Documentation",
            "chore": "Chores",
        }
        for subject in subjects:
            match = re.match(r"^(\w+)(?:\([^)]+\))?!?:\s*(.*)", subject)
            heading = (
                headings.get(match[1], "Other Changes") if match else "Other Changes"
            )
            sections.setdefault(heading, []).append(match[2] if match else subject)
        content = f"## Changes since {previous}\n\n" + "\n\n".join(
            f"### {heading}\n\n" + "\n".join(f"- {subject}" for subject in values)
            for heading, values in sections.items()
        )
    else:
        # Only complete top-level entries in known categories prove coverage.
        # Retain Git changes when custom rendering leaves their identity uncertain.
        change_types = {
            "### New Feature": "feat",
            "### Bug Fixes": "fix",
            "### Refactor": "refactor",
            "### Perf": "perf",
        }
        rendered_entries = set()
        change_type = None
        for line in content.splitlines():
            if line.startswith("#"):
                change_type = change_types.get(line)
            elif change_type and line.startswith("- "):
                rendered_entries.add((change_type, line[2:]))
        rendered_references = {
            reference
            for _, entry in rendered_entries
            for reference in re.findall(r"\(#\d+\)", entry)
        }
        missing = []
        for subject in subjects:
            references = re.findall(r"\(#\d+\)", subject)
            match = re.match(r"^(\w+)(?:\(([^)]+)\))?!?:\s*(.*)", subject)
            rendered_subject = match[3] if match else subject
            if match and match[2]:
                rendered_subject = f"**{match[2]}**: {rendered_subject}"
            entry = (match[1] if match else "", rendered_subject)
            if (
                references
                and any(
                    reference not in rendered_references for reference in references
                )
            ) or (not references and entry not in rendered_entries):
                missing.append(subject)
        if missing:
            content += "\n\n### Other Changes\n\n" + "\n".join(
                f"- {subject}" for subject in missing
            )
    return annotate_product_authors(content, repository)


MAX_COMMITS_PER_DEPENDENCY = 20


MAX_COMMIT_LOOKUP_PAGES = 3


DEPENDENCIES = [
    {
        "name": "markdown-flow",
        "repo": "ai-shifu/markdown-flow-agent-py",
        "path": "src/api/requirements.txt",
        "type": "requirements",
        "registry": "pypi",
    },
    {
        "name": "markdown-flow-ui",
        "repo": "ai-shifu/markdown-flow-ui",
        "path": "src/web/package-lock.json",
        "legacy_path": "src/cook-web/package-lock.json",
        "type": "package_lock",
        "registry": "npm",
    },
]


def git_show(ref: str, path: str) -> str:
    """Read an optional file from a frozen Git object."""
    if not ref:
        return ""

    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return ""


def normalize_version(raw: str) -> str:
    """Extract the pinned dependency version using the existing release pattern."""
    match = re.search(
        r"\d+\.\d+\.\d+(?:[.-][0-9A-Za-z][0-9A-Za-z.-]*)?",
        raw,
    )
    return match.group(0) if match else ""


def extract_version(content: str, dependency: dict[str, str]) -> str:
    """Read Python requirement or npm manifest/lock dependency pins."""
    if not content:
        return ""

    name = dependency["name"]
    if dependency["type"] == "requirements":
        match = re.search(
            rf"(?m)^\s*{re.escape(name)}==\s*([^#;\s]+)",
            content,
        )
        return normalize_version(match.group(1)) if match else ""

    if dependency["type"] == "package_json":
        try:
            package = json.loads(content)
        except json.JSONDecodeError:
            return ""

        for section in (
            "dependencies",
            "devDependencies",
            "optionalDependencies",
            "peerDependencies",
        ):
            raw = (package.get(section) or {}).get(name)
            if raw:
                return normalize_version(str(raw))

    if dependency["type"] == "package_lock":
        try:
            package_lock = json.loads(content)
        except json.JSONDecodeError:
            return ""

        locked_package = (package_lock.get("packages") or {}).get(
            f"node_modules/{name}",
        ) or {}
        raw = locked_package.get("version")
        return normalize_version(str(raw)) if raw else ""

    return ""


def github_json(api_path: str) -> dict | list:
    """Read dependency metadata from the fixed HTTPS GitHub API."""
    token = (
        os.environ.get("GH_TOKEN")
        or os.environ.get("RELEASE_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )
    request = urllib.request.Request(f"https://api.github.com{api_path}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 -- Only fixed GitHub/registry HTTPS URLs are constructed here.
        return json.load(response)


pr_author_cache: dict[tuple[str, int], str] = {}


def fetch_pr_author(repo: str, pr_number: int) -> str:
    """Cache best-effort dependency PR author lookups."""
    cache_key = (repo, pr_number)
    if cache_key in pr_author_cache:
        return pr_author_cache[cache_key]

    try:
        data = github_json(f"/repos/{repo}/pulls/{pr_number}")
    except urllib.error.HTTPError:
        author = ""
    except Exception:
        author = ""
    else:
        login = ((data.get("user") or {}).get("login") or "").strip()
        author = f"@{login}" if login else ""

    pr_author_cache[cache_key] = author
    return author


def fetch_public_json(url: str) -> dict:
    """Read JSON from a registry HTTPS URL constructed by this module."""
    request = urllib.request.Request(url)  # noqa: S310 -- Callers construct only PyPI and npm HTTPS URLs.
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "ai-shifu-release-notes")
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 -- Only fixed GitHub/registry HTTPS URLs are constructed here.
        return json.load(response)


def tag_exists(repo: str, tag: str) -> bool:
    """Distinguish missing dependency tags from failed API requests."""
    encoded_tag = urllib.parse.quote(tag, safe="")
    try:
        github_json(f"/repos/{repo}/git/ref/tags/{encoded_tag}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    return True


def resolve_tag(repo: str, package_name: str, version: str) -> str:
    """Try the existing v-prefixed, bare and package-qualified tag forms."""
    candidates = [
        f"v{version}",
        version,
        f"{package_name}@{version}",
    ]
    for candidate in candidates:
        if tag_exists(repo, candidate):
            return candidate
    return ""


def compare_tags(repo: str, base_tag: str, head_tag: str) -> dict:
    """Compare library tags and reject malformed comparison responses."""
    encoded_base = urllib.parse.quote(base_tag, safe="")
    encoded_head = urllib.parse.quote(head_tag, safe="")
    comparison = github_json(f"/repos/{repo}/compare/{encoded_base}...{encoded_head}")
    if not isinstance(comparison, dict):
        message = f"unexpected compare payload: {type(comparison).__name__}"
        raise TypeError(message)
    return comparison


def package_publish_time(dependency: dict[str, str], version: str) -> str:
    """Resolve registry publication time for the exact pinned version."""
    name = dependency["name"]
    registry = dependency["registry"]
    if registry == "pypi":
        data = fetch_public_json(f"https://pypi.org/pypi/{name}/json")
        uploads = data.get("releases", {}).get(version, [])
        times = sorted(
            upload.get("upload_time_iso_8601", "")
            for upload in uploads
            if upload.get("upload_time_iso_8601")
        )
        return times[-1] if times else ""

    if registry == "npm":
        encoded_name = urllib.parse.quote(name, safe="")
        data = fetch_public_json(f"https://registry.npmjs.org/{encoded_name}")
        return ((data.get("time") or {}).get(version) or "").strip()

    return ""


def format_commit_subject(subject: str) -> str:
    """Normalize whitespace and merge-subject prefixes."""
    subject = re.sub(r"\s+", " ", subject.strip())
    return re.sub(r"^Merge pull request #\d+ from \S+\s*", "", subject)


def is_version_only_commit(subject: str) -> bool:
    """Omit dependency version-only housekeeping from release notes."""
    conventional_prefix = r"(?:feat|fix|chore|build|ci|bump)(?:\([^)]+\))?!?:"
    version_action = r"(?:update|bump|release|set)"
    version_target = r"(?:package\s+)?version(?:\s+number)?"
    version_value = r"v?\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?"
    patterns = [
        rf"^{conventional_prefix}\s+release\b",
        rf"^{conventional_prefix}\s+{version_action}\s+{version_target}\b",
        rf"^{conventional_prefix}\s+{version_target}\s+{version_action}\b",
        rf"^{conventional_prefix}\s+{version_target}\s+{version_value}\b",
    ]
    return any(re.match(pattern, subject, re.IGNORECASE) for pattern in patterns)


def commit_sort_key(index_and_subject: tuple[int, str]) -> tuple[int, int]:
    """Prioritize features, fixes and then other dependency changes."""
    index, subject = index_and_subject
    if re.match(r"^feat(?:\([^)]+\))?!?:", subject, re.IGNORECASE):
        return (0, index)
    if re.match(r"^fix(?:\([^)]+\))?!?:", subject, re.IGNORECASE):
        return (1, index)
    return (2, index)


def link_pr_references(subject: str, repo: str) -> str:
    """Qualify dependency PR references and enrich authors best-effort."""
    pr_pattern = re.compile(r"\(#(\d+)\)")

    def replace(match: re.Match[str]) -> str:
        pr_number = int(match.group(1))
        pr_ref = f"({repo}#{pr_number})"
        author = fetch_pr_author(repo, pr_number)
        return f"{pr_ref} ({author})" if author else pr_ref

    return pr_pattern.sub(replace, subject)


def commits_between_times(repo: str, since: str, until: str) -> list[str]:
    """Scan bounded registry-time commit pages with deduplication."""
    per_page = 100
    page = 1
    commits = []
    while True:
        query = urllib.parse.urlencode(
            {
                "since": since,
                "until": until,
                "per_page": str(per_page),
                "page": str(page),
            },
        )
        page_commits = github_json(f"/repos/{repo}/commits?{query}")
        if not page_commits:
            break
        if not isinstance(page_commits, list):
            message = ""
            if isinstance(page_commits, dict):
                message = str(page_commits.get("message") or "").strip()
            details = f": {message}" if message else ""
            print(
                "::warning::"
                f"Stopped scanning commits for {repo}; GitHub returned "
                f"{type(page_commits).__name__}{details}.",
                file=sys.stderr,
            )
            break

        commits.extend(page_commits)
        if len(page_commits) < per_page:
            break
        if page >= MAX_COMMIT_LOOKUP_PAGES:
            print(
                "::warning::"
                f"Stopped scanning commits for {repo} after "
                f"{MAX_COMMIT_LOOKUP_PAGES} pages.",
                file=sys.stderr,
            )
            break
        page += 1

    subjects = []
    seen_subjects = set()
    for commit in reversed(commits):
        message = ((commit.get("commit") or {}).get("message") or "").splitlines()
        subject = format_commit_subject(message[0] if message else "")
        if not subject or subject in seen_subjects:
            continue
        if is_version_only_commit(subject):
            continue
        seen_subjects.add(subject)
        subjects.append(subject)
    return subjects


def append_commit_subjects(lines: list[str], commits: list[str], repo: str) -> None:
    """Render the existing twenty-line dependency detail limit."""
    if commits:
        ordered_commits = [
            subject for _, subject in sorted(enumerate(commits), key=commit_sort_key)
        ]
        visible_commits = ordered_commits[:MAX_COMMITS_PER_DEPENDENCY]
        if len(ordered_commits) > MAX_COMMITS_PER_DEPENDENCY:
            hidden_count = len(ordered_commits) - (MAX_COMMITS_PER_DEPENDENCY - 1)
            visible_commits = [
                *ordered_commits[: MAX_COMMITS_PER_DEPENDENCY - 1],
                f"...and {hidden_count} more commits",
            ]

        lines.extend(
            f"- {link_pr_references(subject, repo)}" for subject in visible_commits
        )
    else:
        lines.append("- No non-release commit details were returned for this range.")


def build_dependency_section(
    dependency: dict[str, str], previous: str, source: str
) -> list[str]:
    """Compare previous and frozen candidate dependency pins."""
    name = dependency["name"]
    repo = dependency["repo"]
    path = dependency["path"]
    previous_source = git_show(previous, path)
    legacy_path = dependency.get("legacy_path", "")
    if not previous_source and legacy_path:
        previous_source = git_show(previous, legacy_path)
        if previous_source:
            print(
                f"Using legacy dependency path {legacy_path} for {name} at {previous}",
                file=sys.stderr,
            )
    previous_version = extract_version(previous_source, dependency)
    current_version = extract_version(git_show(source, path), dependency)

    if not previous_version or not current_version:
        return []
    if previous_version == current_version:
        return []

    lines = [
        f"### `{name}` `{previous_version}` -> `{current_version}`",
    ]

    try:
        base_tag = ""
        head_tag = ""
        try:
            base_tag = resolve_tag(repo, name, previous_version)
            head_tag = resolve_tag(repo, name, current_version)
        except Exception as error:
            print(
                f"::warning::Failed to resolve GitHub tags for {name}: {error}",
                file=sys.stderr,
            )

        if base_tag and head_tag:
            try:
                comparison = compare_tags(repo, base_tag, head_tag)
            except Exception as error:
                print(
                    f"::warning::Failed to compare GitHub tags for {name}: {error}",
                    file=sys.stderr,
                )
            else:
                compare_url = comparison.get("html_url") or (
                    f"https://github.com/{repo}/compare/"
                    f"{urllib.parse.quote(base_tag, safe='')}..."
                    f"{urllib.parse.quote(head_tag, safe='')}"
                )
                lines.append(f"Compare: [`{base_tag}...{head_tag}`]({compare_url})")

                commits = []
                seen_subjects = set()
                for commit in comparison.get("commits", []):
                    message = (
                        (commit.get("commit") or {}).get("message") or ""
                    ).splitlines()
                    subject = format_commit_subject(message[0] if message else "")
                    if not subject or subject in seen_subjects:
                        continue
                    if is_version_only_commit(subject):
                        continue
                    seen_subjects.add(subject)
                    commits.append(subject)
                append_commit_subjects(lines, commits, repo)
                return lines

        previous_time = package_publish_time(dependency, previous_version)
        current_time = package_publish_time(dependency, current_version)
        if previous_time and current_time:
            append_commit_subjects(
                lines,
                commits_between_times(repo, previous_time, current_time),
                repo,
            )
        else:
            lines.append(
                "- Version changed, but matching GitHub tags and package publish "
                "times were not found for one or both pinned versions.",
            )
    except Exception as error:
        print(
            f"::warning::Failed to build MarkdownFlow changelog for {name}: {error}",
            file=sys.stderr,
        )
        lines.append("- Version changed, but release note lookup failed.")

    return lines


def dependency_notes(previous: str, source: str) -> str:
    """Preserve dependency notes while reading both pins at frozen Git revisions."""
    if not previous:
        return ""
    sections = [
        "\n".join(section)
        for dependency in DEPENDENCIES
        if (section := build_dependency_section(dependency, previous, source))
    ]
    return (
        "## MarkdownFlow Dependency Updates\n\n" + "\n\n".join(sections)
        if sections
        else ""
    )


def generate_notes(source: str, version: str, repository: str) -> str:
    """Render notes and installation/docs links for the exact candidate, not main."""
    source_commit(source)
    version_tuple(version)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        message = "Repository must be owner/name"
        raise ValueError(message)
    previous = previous_tag(source, version)
    content = product_notes(source, previous, repository)
    dependencies = dependency_notes(previous, source)
    if dependencies:
        content += "\n\n" + dependencies
    tag, name = f"v{version}", repository.rsplit("/", maxsplit=1)[-1]
    url = f"https://github.com/{repository}"
    return f"""{content}

Source commit: `{source}`

## Installation from Source

```bash
git clone {url}.git
cd {name}
git checkout {tag}
cd docker
cp .env.example.full .env
# Configure a provider API key in .env and set LLM_MODEL_1_ID
# to a text model served by that provider (required; no default).
# LLM_MODEL_1_NAME is optional; an empty name displays the configured model ID.
docker compose up
```

Existing installations must configure model 1 and follow
[Upgrading to numbered models]({url}/blob/{tag}/INSTALL_MANUAL.md#upgrading-to-numbered-models)
before starting the new API or workers.

## Documentation

- [README]({url}/blob/{tag}/README.md)
- [Contributing Guidelines]({url}/blob/{tag}/CONTRIBUTING.md)
- [Changelog]({url}/releases)

## Support

- [Report Issues]({url}/issues)
- [Discussions]({url}/discussions)
- [Give us a star]({url}) if this project helped you!
"""


def main() -> None:
    """Write arbitrary release text to a file, never to Actions output delimiters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--pr-body",
        action="store_true",
        help="Include the PR-only manual-merge handoff",
    )
    args = parser.parse_args()
    content = generate_notes(args.source, args.version, args.repository)
    if args.pr_body:
        content = (
            f"This PR prepares release v{args.version}; it creates no formal tag or Release.\n\n"
            "A human must review CI and manually merge this PR into main.\n"
            "AI/scripts must never merge. Never enable auto-merge for a release PR.\n"
            "Merging main retains the existing latest-image and production CICD/Drone triggers.\n\n"
            "After merge, automation validates the exact merged commit and creates a draft only.\n"
            "A human must review and manually Publish that draft in GitHub to start release-image publication.\n\n"
            "## Changelog preview\n\nThis preview is recomputed at the exact merged main commit.\n\n"
            + content
        )
    args.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
