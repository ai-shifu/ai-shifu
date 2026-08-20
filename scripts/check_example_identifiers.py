#!/usr/bin/env python3
"""Reject account-scoped identifiers copied into repository examples."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

VOLCENGINE_VOICE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<value>S_[A-Za-z0-9_-]{4,64})"
    r"(?![A-Za-z0-9_-])"
)
VOLCENGINE_VOICE_CONTEXT_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:voice[_ -]?id|speaker[_ -]?(?:id|slots?)|"
    r"(?:\u58f0\u97f3|\u97f3\u8272|\u8bf4\u8bdd\u4eba)\s*"
    r"(?:id|\u7f16\u53f7|\u69fd\u4f4d)|"
    r"voiceIdPlaceholderVolcengine|query_volcengine_voice_status|"
    r"verify_volcengine_voice_id)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
VOLCENGINE_PROVIDER_CONTEXT_RE = re.compile(
    r"(?:volcengine|\u706b\u5c71\u5f15\u64ce)", re.IGNORECASE
)
GENERIC_S_CONSTANT_RE = re.compile(r"^S_[A-Z][A-Z0-9_]*$")
MASKED_VOLCENGINE_VOICE_ID_RE = re.compile(r"^S_x{4,64}$")
MINIMAX_OPAQUE_VOICE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<value>AiShifu_[0-9A-Fa-f]{12,64})"
    r"(?![A-Za-z0-9_-])"
)
MINIMAX_GENERATED_VOICE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?P<value>AiShifu_[A-Za-z0-9_]{1,13}_[0-9A-Fa-f]{8})"
    r"(?![A-Za-z0-9_-])"
)
MINIMAX_RUNTIME_VOICE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?P<value>AiShifu_[A-Za-z0-9_-]{0,55}[A-Za-z0-9])"
    r"(?![A-Za-z0-9_-])"
)
INTENTIONAL_MINIMAX_TEST_VOICE_IDS = {
    "AiShifu_" + suffix
    for suffix in (
        "clone_1",
        "deleted_1",
        "detached_1",
        "does_not_exist",
        "failed_1",
        "filter_mm",
        "manual_voice",
        "missing_voice",
        "no_row_here",
        "not_a_speaker",
        "not_teacher",
        "other_voice",
        "owned_voice",
        "processing_voice",
        "ready_1",
        "ready_2",
        "ready_owned",
        "ready_voice",
        "reusable_1",
        "route_1",
        "route_low_balance",
        "route_queued_1",
        "saved_voice_1",
        "shared_id",
        "teacher_1",
        "teacher_2",
        "teacher_a",
        "teacher_retry_1",
        "teacher_storage_1",
        "teacher_voice",
        "unknown_voice",
        "voice_1",
        "voice_123",
    )
}
WECHAT_APP_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<value>wx[0-9A-Fa-f]{16})(?![A-Za-z0-9_])"
)
WECHAT_APP_ID_EXAMPLE_RE = re.compile(
    r"(?:\bNEXT_PUBLIC_WECHAT_APP_ID\s*=\s*[\"']?|"
    r"[\"']?wechatAppId[\"']?\s*:\s*[\"'])"
    r"(?P<value>wx[A-Za-z0-9_-]{16})(?![A-Za-z0-9_-])"
)
UMAMI_SITE_ID_RE = re.compile(
    r"(?:umamiWebsiteId|(?:NEXT_PUBLIC_)?ANALYTICS_UMAMI_SITE_ID)"
    r"[\"']?\s*[:=]\s*[\"']?"
    r"(?P<value>[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-"
    r"[A-Za-z0-9]{4}-[A-Za-z0-9]{12})",
    re.IGNORECASE,
)
UMAMI_SCRIPT_URL_RE = re.compile(
    r"(?:umamiScriptSrc|(?:NEXT_PUBLIC_)?ANALYTICS_UMAMI_SCRIPT)"
    r"[\"']?\s*[:=]\s*[\"']?(?P<value>https?://[^\s\"']+)",
    re.IGNORECASE,
)
HOME_URL_ASSIGNMENT_RE = re.compile(
    r"(?:\bHOME_URL|[\"']?homeUrl[\"']?)\s*[:=]\s*[\"']?"
    r"(?P<url>[^\s\"',}]+)",
    re.IGNORECASE,
)
HOME_URL_COURSE_ID_RES = (
    re.compile(r"/c/(?P<value>[A-Za-z0-9_-]{24,64})(?![A-Za-z0-9_-])"),
    re.compile(
        r"[?&]courseId=(?P<value>[A-Za-z0-9_-]{24,64})"
        r"(?![A-Za-z0-9_-])",
        re.IGNORECASE,
    ),
)
FEISHU_RESOURCE_RE = re.compile(
    r"(?P<value>https?://[A-Za-z0-9.-]+\.feishu\.cn/"
    r"(?:base|docx|sheets|wiki|share/base/form)/[A-Za-z0-9]+)"
)

MASKED_MINIMAX_VOICE_ID = "AiShifu_xxxxxxxxxx"
MASKED_WECHAT_APP_ID = "wx" + ("x" * 16)
MASKED_UMAMI_SITE_ID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
MASKED_COURSE_ID = "x" * 32
INTENTIONAL_PUBLIC_FEISHU_RESOURCES = {
    "https://zhentouai.feishu.cn/wiki/AUE5wpipJi5bL4k6GticmxddnPb",
    "https://zhentouai.feishu.cn/share/base/form/shrcnwp8SRl1ghzia4fBG08VYkh",
}


@dataclass(frozen=True, order=True)
class IdentifierViolation:
    """Describe a detected identifier violation."""

    path: str
    line: int
    message: str

    def __str__(self) -> str:
        """Return the violation in path-and-line form."""
        return f"{self.path}:{self.line}: {self.message}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_containing(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start:] if end == -1 else text[start:end]


def _volcengine_context(text: str, match: re.Match[str]) -> str:
    value_offset = match.start("value")
    current_line = _line_containing(text, value_offset)
    value_start = value_offset - (text.rfind("\n", 0, value_offset) + 1)
    value_end = value_start + len(match.group("value"))
    prefix = current_line[:value_start]
    suffix = current_line[value_end:]
    is_standalone_value = re.fullmatch(
        r"\s*(?:[-*]\s*)?[`\"']?", prefix
    ) and re.fullmatch(r"[`\"']?\s*[,;]?\s*", suffix)
    has_voice_context = VOLCENGINE_VOICE_CONTEXT_RE.search(current_line)
    needs_nearby_context = bool(is_standalone_value or has_voice_context)
    if not needs_nearby_context:
        return current_line

    current_start = text.rfind("\n", 0, value_offset) + 1
    previous_lines = text[:current_start].splitlines()
    nearby_lines: list[str] = []
    for line in reversed(previous_lines):
        if not line.strip():
            continue
        nearby_lines.append(line)
        if len(nearby_lines) == 3:
            break
    nearby_lines.reverse()
    return "\n".join([*nearby_lines, current_line])


def _is_test_fixture_path(path: str) -> bool:
    normalized = Path(path)
    parts = {part.lower() for part in normalized.parts}
    filename = normalized.name.lower()
    return (
        bool(parts & {"test", "tests"})
        or filename.startswith("test_")
        or ".test." in filename
        or ".spec." in filename
    )


def _append_match(
    violations: list[IdentifierViolation],
    *,
    path: str,
    text: str,
    match: re.Match[str],
    message: str,
) -> None:
    violations.append(
        IdentifierViolation(
            path=path,
            line=_line_number(text, match.start("value")),
            message=message,
        )
    )


def find_violations_in_text(path: str, text: str) -> list[IdentifierViolation]:
    """Return identifier-example violations for one UTF-8 text file."""
    violations: list[IdentifierViolation] = []

    for match in VOLCENGINE_VOICE_ID_RE.finditer(text):
        context = _volcengine_context(text, match)
        has_provider_context = VOLCENGINE_PROVIDER_CONTEXT_RE.search(context)
        if not (has_provider_context or VOLCENGINE_VOICE_CONTEXT_RE.search(context)):
            continue
        value = match.group("value")
        if MASKED_VOLCENGINE_VOICE_ID_RE.fullmatch(value):
            continue
        if GENERIC_S_CONSTANT_RE.fullmatch(value) and not has_provider_context:
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=(
                f"Volcengine Voice ID {value!r} is not visibly masked; "
                "use S_ followed only by x characters"
            ),
        )

    reported_minimax_offsets: set[int] = set()
    for match in MINIMAX_OPAQUE_VOICE_ID_RE.finditer(text):
        reported_minimax_offsets.add(match.start("value"))
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=(
                f"MiniMax-style opaque Voice ID {match.group('value')!r} "
                f"looks account-scoped; use {MASKED_MINIMAX_VOICE_ID}"
            ),
        )

    for match in MINIMAX_GENERATED_VOICE_ID_RE.finditer(text):
        if match.start("value") in reported_minimax_offsets:
            continue
        reported_minimax_offsets.add(match.start("value"))
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=(
                f"Generated-format MiniMax Voice ID {match.group('value')!r} "
                f"looks account-scoped; use {MASKED_MINIMAX_VOICE_ID}"
            ),
        )

    for match in MINIMAX_RUNTIME_VOICE_ID_RE.finditer(text):
        value = match.group("value")
        is_semantic_test_fixture = (
            _is_test_fixture_path(path) and value in INTENTIONAL_MINIMAX_TEST_VOICE_IDS
        )
        if (
            match.start("value") in reported_minimax_offsets
            or value == MASKED_MINIMAX_VOICE_ID
            or is_semantic_test_fixture
        ):
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=(
                f"MiniMax Voice ID {value!r} is not visibly masked; "
                f"use {MASKED_MINIMAX_VOICE_ID}"
            ),
        )

    for match in WECHAT_APP_ID_RE.finditer(text):
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=f"WeChat App ID example must use {MASKED_WECHAT_APP_ID}",
        )

    for match in WECHAT_APP_ID_EXAMPLE_RE.finditer(text):
        value = match.group("value")
        if value == MASKED_WECHAT_APP_ID or WECHAT_APP_ID_RE.fullmatch(value):
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=f"WeChat App ID example must use {MASKED_WECHAT_APP_ID}",
        )

    for match in UMAMI_SITE_ID_RE.finditer(text):
        if match.group("value") == MASKED_UMAMI_SITE_ID:
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=f"Umami website ID example must use {MASKED_UMAMI_SITE_ID}",
        )

    for match in UMAMI_SCRIPT_URL_RE.finditer(text):
        hostname = (urlparse(match.group("value")).hostname or "").lower()
        if hostname == "example.test" or hostname.endswith(".example.test"):
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message="Umami script example must use an example.test host",
        )

    for assignment in HOME_URL_ASSIGNMENT_RE.finditer(text):
        url = assignment.group("url")
        for course_id_re in HOME_URL_COURSE_ID_RES:
            for match in course_id_re.finditer(url):
                if match.group("value") == MASKED_COURSE_ID:
                    continue
                violations.append(
                    IdentifierViolation(
                        path=path,
                        line=_line_number(
                            text,
                            assignment.start("url") + match.start("value"),
                        ),
                        message=(
                            f"HOME_URL course ID example must use {MASKED_COURSE_ID}"
                        ),
                    )
                )

    for match in FEISHU_RESOURCE_RE.finditer(text):
        if match.group("value") in INTENTIONAL_PUBLIC_FEISHU_RESOURCES:
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=(
                "Unreviewed Feishu resource locator; remove incidental links or "
                "explicitly allowlist an intentional public product destination"
            ),
        )

    return violations


def _repository_relative_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _index_entries() -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    entries: list[tuple[str, str]] = []
    for raw_entry in result.stdout.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode, raw_object_id, stage = metadata.split(b" ", 2)
        if stage != b"0" or mode == b"160000":
            continue
        entries.append(
            (
                raw_path.decode("utf-8", errors="surrogateescape"),
                raw_object_id.decode("ascii"),
            )
        )
    return entries


def _read_index_objects(object_ids: list[str]) -> dict[str, bytes]:
    unique_object_ids = list(dict.fromkeys(object_ids))
    if not unique_object_ids:
        return {}
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        check=True,
        input="".join(f"{object_id}\n" for object_id in unique_object_ids).encode(),
        capture_output=True,
    )
    objects: dict[str, bytes] = {}
    offset = 0
    for object_id in unique_object_ids:
        header_end = result.stdout.find(b"\n", offset)
        if header_end == -1:
            raise OSError("git cat-file returned a truncated header")
        header = result.stdout[offset:header_end].split()
        if len(header) != 3 or header[1] != b"blob":
            message = f"git cat-file did not return blob {object_id}"
            raise OSError(message)
        size = int(header[2])
        content_start = header_end + 1
        content_end = content_start + size
        if result.stdout[content_end : content_end + 1] != b"\n":
            raise OSError("git cat-file returned a truncated blob")
        objects[object_id] = result.stdout[content_start:content_end]
        offset = content_end + 1
    return objects


def _index_candidates() -> list[tuple[str, bytes]]:
    entries = _index_entries()
    objects = _read_index_objects([object_id for _, object_id in entries])
    return [(path, objects[object_id]) for path, object_id in entries]


def find_violations(
    paths: list[Path] | None = None,
    *,
    staged: bool = False,
    validate_fixtures: bool = True,
) -> list[IdentifierViolation]:
    """Scan repository text files, or the explicitly supplied paths."""
    if validate_fixtures:
        run_self_test()

    violations: list[IdentifierViolation] = []
    if paths is not None and staged:
        raise ValueError("explicit paths cannot be combined with staged content")

    if paths is not None:
        candidates = [
            (path.as_posix(), path.read_bytes()) for path in paths if path.is_file()
        ]
    elif staged:
        candidates = _index_candidates()
    else:
        candidates = []
        for relative_path in _repository_relative_paths():
            path = ROOT / relative_path
            if path.is_file():
                candidates.append((relative_path, path.read_bytes()))

    for path_label, raw in candidates:
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        violations.extend(find_violations_in_text(path_label, text))
    return sorted(violations)


def run_self_test() -> None:
    suspicious_volcengine = "S_" + "a1b2c3d4"
    suspicious_volcengine_hyphen = "S_" + "-abcd"
    suspicious_volcengine_underscore = "S_" + "_abcd"
    status_like_volcengine = "S_" + "READY"
    suspicious_minimax = "AiShifu_" + "0123456789ab"
    suspicious_minimax_non_hex = "AiShifu_" + "abcd_20260618_x1"
    suspicious_minimax_generated = "AiShifu_" + "teacher_89abcdef"
    semantic_minimax_fixture = "AiShifu_" + "ready_voice"
    suspicious_wechat = "wx" + "1234567890abcdef"
    wrong_masked_wechat = "wx" + ("y" * 16)
    suspicious_umami = "12345678-1234-4abc-8def-1234567890ab"
    wrong_masked_umami = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
    suspicious_umami_script = "https://analytics." + "internal.test/script.js"
    suspicious_course = "1234567890abcdef" * 2
    wrong_masked_course = "y" * 32
    suspicious_doc = "https://internal." + "feishu.cn/docx/" + "AbCdEfGhIjKlMnOp"
    suspicious_base = "https://internal." + "feishu.cn/base/" + "AbCdEfGhIjKlMnOp"
    suspicious_sheet = "https://internal." + "feishu.cn/sheets/" + "AbCdEfGhIjKlMnOp"

    assert find_violations_in_text(
        "fixture.py", f'voice_id = "{suspicious_volcengine}"'
    )
    assert not find_violations_in_text("fixture.py", 'voice_id = "S_xxxx"')
    assert not find_violations_in_text("fixture.py", 'voice_id = "S_xxxxxxxxxx"')
    assert not find_violations_in_text("fixture.py", f'voice_id = "S_{"x" * 64}"')
    assert find_violations_in_text(
        "fixture.py", f'voice_id = "{suspicious_volcengine_hyphen}"'
    )
    assert find_violations_in_text(
        "fixture.py", f'voice_id = "{suspicious_volcengine_underscore}"'
    )
    assert not find_violations_in_text("fixture.py", status_like_volcengine)
    assert not find_violations_in_text("fixture.py", "S_ALPHA_1")
    assert not find_violations_in_text(
        "fixture.py", f'voice_id = "{status_like_volcengine}"'
    )
    assert not find_violations_in_text(
        "fixture.py", f"last_voice_id = {status_like_volcengine}"
    )
    assert find_violations_in_text(
        "fixture.env", f"VOLCENGINE_VOICE_ID={status_like_volcengine}"
    )
    assert find_violations_in_text(
        "fixture.py",
        f'provider = "volcengine"\nlast_voice_id = {status_like_volcengine}',
    )
    assert find_violations_in_text(
        "fixture.md", f"Volcengine speaker ID: {suspicious_volcengine}"
    )
    assert find_violations_in_text(
        "fixture.env", f"VOLCENGINE_VOICE_ID={suspicious_volcengine}"
    )
    assert find_violations_in_text(
        "fixture.py",
        f'is_volcengine_cloned_speaker_id("{suspicious_volcengine}")',
    )
    assert find_violations_in_text(
        "fixture.md", f"Volcengine Voice ID:\n{suspicious_volcengine}"
    )
    assert find_violations_in_text(
        "fixture.md",
        f"\u706b\u5c71\u5f15\u64ce\u58f0\u97f3 ID\uff1a{suspicious_volcengine}",
    )
    assert find_violations_in_text(
        "fixture.md",
        f"Volcengine speaker ID:\n```text\n{suspicious_volcengine}\n```",
    )
    assert not find_violations_in_text(
        "fixture.py", f"{status_like_volcengine} = 'ready'\nvoice_id = 'other'"
    )
    assert find_violations_in_text("fixture.py", f'voice_id = "{suspicious_minimax}"')
    assert find_violations_in_text(
        "docs/fixture.md", f'voice_id = "{suspicious_minimax_non_hex}"'
    )
    assert find_violations_in_text(
        "src/api/tests/test_fixture.py",
        f'voice_id = "{suspicious_minimax_non_hex}"',
    )
    assert find_violations_in_text(
        "src/api/tests/test_fixture.py",
        'voice_id = "AiShifu_' + 'sunner_89abcdeg"',
    )
    assert not find_violations_in_text(
        "src/api/tests/test_fixture.py", f'voice_id = "{semantic_minimax_fixture}"'
    )
    assert find_violations_in_text(
        "src/api/tests/test_fixture.py", f'voice_id = "{suspicious_minimax}"'
    )
    assert find_violations_in_text(
        "src/api/tests/test_fixture.py",
        f'voice_id = "{suspicious_minimax_generated}"',
    )
    assert not find_violations_in_text(
        "fixture.py", f'voice_id = "{MASKED_MINIMAX_VOICE_ID}"'
    )
    assert find_violations_in_text(
        "fixture.md", f"NEXT_PUBLIC_WECHAT_APP_ID={suspicious_wechat}"
    )
    assert find_violations_in_text(
        "fixture.md", f"NEXT_PUBLIC_WECHAT_APP_ID={wrong_masked_wechat}"
    )
    assert not find_violations_in_text(
        "fixture.md", f"NEXT_PUBLIC_WECHAT_APP_ID={MASKED_WECHAT_APP_ID}"
    )
    assert find_violations_in_text(
        "fixture.md", f"NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID={suspicious_umami}"
    )
    assert find_violations_in_text(
        "fixture.md",
        f"NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID={wrong_masked_umami}",
    )
    assert not find_violations_in_text(
        "fixture.md",
        f"NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID={MASKED_UMAMI_SITE_ID}",
    )
    assert find_violations_in_text(
        "fixture.env", f"ANALYTICS_UMAMI_SITE_ID={suspicious_umami}"
    )
    assert not find_violations_in_text(
        "fixture.env", f"ANALYTICS_UMAMI_SITE_ID={MASKED_UMAMI_SITE_ID}"
    )
    assert find_violations_in_text(
        "fixture.md", f"umamiScriptSrc: {suspicious_umami_script}"
    )
    assert not find_violations_in_text(
        "fixture.md", "umamiScriptSrc: https://analytics.example.test/script.js"
    )
    assert find_violations_in_text(
        "fixture.env", f"ANALYTICS_UMAMI_SCRIPT={suspicious_umami_script}"
    )
    assert not find_violations_in_text(
        "fixture.env",
        "ANALYTICS_UMAMI_SCRIPT=https://analytics.example.test/script.js",
    )
    assert find_violations_in_text("fixture.md", f"HOME_URL=/c/{suspicious_course}")
    assert find_violations_in_text("fixture.md", f"HOME_URL=/c/{wrong_masked_course}")
    assert not find_violations_in_text("fixture.md", f"HOME_URL=/c/{MASKED_COURSE_ID}")
    assert find_violations_in_text(
        "fixture.md",
        f"HOME_URL=https://app.example.test/c/{suspicious_course}",
    )
    assert not find_violations_in_text(
        "fixture.md",
        f"HOME_URL=https://app.example.test/c/{MASKED_COURSE_ID}",
    )
    assert find_violations_in_text(
        "fixture.md", f"HOME_URL=/c?courseId={suspicious_course}"
    )
    assert not find_violations_in_text(
        "fixture.md", f"HOME_URL=/c?courseId={MASKED_COURSE_ID}"
    )
    assert find_violations_in_text("fixture.ts", suspicious_doc)
    assert find_violations_in_text("fixture.md", suspicious_doc)
    assert find_violations_in_text("fixture.md", suspicious_base)
    assert find_violations_in_text("fixture.md", suspicious_sheet)
    assert not find_violations_in_text(
        "fixture.ts", next(iter(INTENTIONAL_PUBLIC_FEISHU_RESOURCES))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic checker fixtures before scanning the repository.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan the complete Git index snapshot instead of the worktree.",
    )
    args = parser.parse_args()

    if args.self_test:
        run_self_test()

    try:
        violations = find_violations(
            staged=args.staged,
            validate_fixtures=not args.self_test,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Identifier example validation could not run: {exc}", file=sys.stderr)
        return 1

    if violations:
        print("Identifier example validation failed:", file=sys.stderr)
        for violation in violations:
            print(f" - {violation}", file=sys.stderr)
        return 1

    print("Identifier example validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
