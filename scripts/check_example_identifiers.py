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
MASKED_VOLCENGINE_VOICE_ID_RE = re.compile(r"^S_x{4,64}$")
MINIMAX_OPAQUE_VOICE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<value>AiShifu_[0-9A-Fa-f]{12,64})"
    r"(?![A-Za-z0-9_-])"
)
WECHAT_APP_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<value>wx[0-9A-Fa-f]{16})(?![A-Za-z0-9_])"
)
WECHAT_APP_ID_EXAMPLE_RE = re.compile(
    r"(?:\bNEXT_PUBLIC_WECHAT_APP_ID\s*=\s*[\"']?|"
    r"[\"']?wechatAppId[\"']?\s*:\s*[\"'])"
    r"(?P<value>wx[A-Za-z0-9_-]{16})(?![A-Za-z0-9_-])"
)
UMAMI_SITE_ID_RE = re.compile(
    r"(?:umamiWebsiteId|NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID)"
    r"[\"']?\s*[:=]\s*[\"']?"
    r"(?P<value>[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-"
    r"[A-Za-z0-9]{4}-[A-Za-z0-9]{12})",
    re.IGNORECASE,
)
UMAMI_SCRIPT_URL_RE = re.compile(
    r"(?:umamiScriptSrc|NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT)"
    r"[\"']?\s*[:=]\s*[\"']?(?P<value>https?://[^\s\"']+)",
    re.IGNORECASE,
)
HOME_COURSE_ID_RE = re.compile(
    r"(?:\bHOME_URL\s*=\s*[\"']?|[\"']?homeUrl[\"']?\s*:\s*[\"']?)"
    r"/c/(?P<value>[A-Za-z0-9_-]{24,64})(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)
FEISHU_RESOURCE_RE = re.compile(
    r"(?P<value>https?://[A-Za-z0-9.-]+\.feishu\.cn/"
    r"(?:docx|wiki|share/base/form)/[A-Za-z0-9]+)"
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
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


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
        value = match.group("value")
        if MASKED_VOLCENGINE_VOICE_ID_RE.fullmatch(value):
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

    for match in MINIMAX_OPAQUE_VOICE_ID_RE.finditer(text):
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

    for match in HOME_COURSE_ID_RE.finditer(text):
        if match.group("value") == MASKED_COURSE_ID:
            continue
        _append_match(
            violations,
            path=path,
            text=text,
            match=match,
            message=f"HOME_URL course ID example must use {MASKED_COURSE_ID}",
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


def _repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def find_violations(paths: list[Path] | None = None) -> list[IdentifierViolation]:
    """Scan repository text files, or the explicitly supplied paths."""

    violations: list[IdentifierViolation] = []
    files = paths if paths is not None else _repository_files()
    for path in files:
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        try:
            relative_path = path.relative_to(ROOT).as_posix()
        except ValueError:
            relative_path = path.as_posix()
        violations.extend(find_violations_in_text(relative_path, text))
    return sorted(violations)


def _run_self_test() -> None:
    suspicious_volcengine = "S_" + "a1b2c3d4"
    suspicious_volcengine_hyphen = "S_" + "-abcd"
    suspicious_volcengine_underscore = "S_" + "_abcd"
    suspicious_minimax = "AiShifu_" + "0123456789ab"
    suspicious_wechat = "wx" + "1234567890abcdef"
    wrong_masked_wechat = "wx" + ("y" * 16)
    suspicious_umami = "12345678-1234-4abc-8def-1234567890ab"
    wrong_masked_umami = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
    suspicious_umami_script = "https://analytics." + "internal.test/script.js"
    suspicious_course = "1234567890abcdef" * 2
    wrong_masked_course = "y" * 32
    suspicious_doc = "https://internal." + "feishu.cn/docx/" + "AbCdEfGhIjKlMnOp"

    assert find_violations_in_text(
        "fixture.py", f'voice_id = "{suspicious_volcengine}"'
    )
    assert not find_violations_in_text("fixture.py", 'voice_id = "S_xxxx"')
    assert not find_violations_in_text("fixture.py", 'voice_id = "S_xxxxxxxxxx"')
    assert not find_violations_in_text("fixture.py", f'voice_id = "S_{"x" * 64}"')
    assert find_violations_in_text("fixture.py", suspicious_volcengine_hyphen)
    assert find_violations_in_text("fixture.py", suspicious_volcengine_underscore)
    assert find_violations_in_text("fixture.py", f'voice_id = "{suspicious_minimax}"')
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
        "fixture.md", f"umamiScriptSrc: {suspicious_umami_script}"
    )
    assert not find_violations_in_text(
        "fixture.md", "umamiScriptSrc: https://analytics.example.test/script.js"
    )
    assert find_violations_in_text("fixture.md", f"HOME_URL=/c/{suspicious_course}")
    assert find_violations_in_text("fixture.md", f"HOME_URL=/c/{wrong_masked_course}")
    assert not find_violations_in_text("fixture.md", f"HOME_URL=/c/{MASKED_COURSE_ID}")
    assert find_violations_in_text("fixture.ts", suspicious_doc)
    assert find_violations_in_text("fixture.md", suspicious_doc)
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
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()

    try:
        violations = find_violations()
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
