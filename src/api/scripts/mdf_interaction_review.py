#!/usr/bin/env python3
"""Build a local, self-contained review page from interaction evaluation reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt

if TYPE_CHECKING:
    from collections.abc import Sequence

    from markdown_it.token import Token
    from markdown_it.utils import EnvType, OptionsDict

    from scripts.evaluate_mdf_interactions import Case


ASSETS = Path(__file__).with_name("mdf_interactions")
API_DIR = ASSETS.parents[1]
LABELS_PATH = API_DIR.parent / "i18n/mdf-interaction-review.zh-CN.json"
REPORT_FIELDS = (
    "mode",
    "model",
    "temperature",
    "question_judge",
    "prompt_sha256",
    "cases_sha256",
    "results",
)


def fixture_context(cases: list[Case]) -> dict[str, dict]:
    """Keep authored prompts and learner actions alongside saved results."""
    context = {}
    for case in cases:
        first_line = case.teaching_prompt.strip().partition("\n")[0]
        title = re.fullmatch(r"<!--\s*(.*?)\s*-->", first_line)
        context[case.id] = {
            "title": title[1] if title else case.id,
            "locale": case.locale,
            "teaching_prompt": case.teaching_prompt,
            "course_prompt": case.course_prompt,
            "memory": case.memory,
            "steps": [
                step.model_dump(mode="json", exclude_unset=True) for step in case.steps
            ],
        }
    return context


def legacy_context(
    report: dict, catalog: list[Case], *, require_match: bool = False
) -> dict[str, dict]:
    """Match a historical report to its original sanitized fixture selection."""
    from scripts.evaluate_mdf_interactions import catalog_sha256

    case_ids = {row["case_id"] for row in report["results"]}
    selected = [case for case in catalog if case.id in case_ids]
    if catalog_sha256(selected) != report["cases_sha256"]:
        if require_match:
            msg = "the original fixture catalog does not match the report fingerprint"
            raise ValueError(msg)
        return {}
    return fixture_context(selected)


class SlideText(HTMLParser):
    """Extract readable text from model-authored visuals without rendering them."""

    HIDDEN = frozenset({"script", "style", "template", "iframe", "noscript"})
    BLOCKS = frozenset(
        {"br", "div", "header", "section", "p", "li", "tr", "h1", "h2", "h3", "h4"}
    )

    def __init__(self) -> None:
        """Keep parsed text and track hidden element boundaries."""
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        """Separate block content and discard active source text."""
        if tag in self.HIDDEN:
            self.hidden.append(tag)
        elif not self.hidden and tag in self.BLOCKS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Resume collecting text after the hidden element closes."""
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()
        elif not self.hidden and tag in self.BLOCKS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        """Collect plain text outside hidden elements."""
        if not self.hidden:
            self.chunks.append(data)


def _markdown(slide_label: str) -> MarkdownIt:
    markdown = MarkdownIt("commonmark", {"html": True}).disable(
        ["image", "link", "autolink"]
    )

    def html_block(
        tokens: Sequence[Token], index: int, _options: OptionsDict, _env: EnvType
    ) -> str:
        fragment = tokens[index].content
        reader = SlideText()
        try:
            reader.feed(fragment)
        except AssertionError:
            # HTMLParser raises on some malformed declarations inside generated blocks.
            return f"<pre>{escape(fragment)}</pre>"
        lines = [
            line.strip() for line in "".join(reader.chunks).splitlines() if line.strip()
        ]
        if not lines:
            return ""
        items = "".join(f"<li>{escape(line)}</li>" for line in lines)
        return f'<div class="slide-text"><strong>{escape(slide_label)}</strong><ul>{items}</ul></div>'

    def html_inline(
        tokens: Sequence[Token], index: int, _options: OptionsDict, _env: EnvType
    ) -> str:
        return escape(tokens[index].content)

    markdown.renderer.rules["html_block"] = html_block
    markdown.renderer.rules["html_inline"] = html_inline
    return markdown


def _run_data(report: dict, markdown: MarkdownIt) -> dict:
    if report.get("schema_version") != 5 or not report.get("results"):
        msg = "expected a nonempty interaction evaluation report with schema version 5"
        raise ValueError(msg)
    fields = {key: report[key] for key in REPORT_FIELDS}
    # Legacy runs have no generated ID. Ignore derived context, comparison and summary.
    identity = (
        report.get("run_id")
        or hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    )
    identifiers = set()
    results = []
    for result in fields["results"]:
        key = (result["case_id"], result["repeat"])
        if key in identifiers:
            msg = f"duplicate case and repeat in report: {key}"
            raise ValueError(msg)
        identifiers.add(key)
        results.append(
            {
                **result,
                "steps": [
                    {**step, "rendered_prose": markdown.render(step["prose"])}
                    for step in result["steps"]
                ],
            }
        )
    return {**fields, "results": results, "id": identity}


def write_review(path: Path, reports: list[dict], *, focus: str | None = None) -> None:
    """Write a review page for distinct runs with the same selected fixtures."""
    if not reports or len({report["cases_sha256"] for report in reports}) != 1:
        msg = "all reports must use the same selected fixture fingerprint"
        raise ValueError(msg)
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    markdown = _markdown(labels["slideText"])
    runs = [_run_data(report, markdown) for report in reports]
    if len({run["id"] for run in runs}) != len(runs):
        msg = "each report in a review must come from a distinct run"
        raise ValueError(msg)
    context = next(
        (
            report["review_context"]
            for report in reports
            if report.get("review_context")
        ),
        {},
    )
    payload = json.dumps(
        {"runs": runs, "context": context, "labels": labels, "focus": focus},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).replace("<", r"\u003c")
    template = (ASSETS / "review.html").read_text(encoding="utf-8")
    css = (ASSETS / "review.css").read_text(encoding="utf-8")
    js = (ASSETS / "review.js").read_text(encoding="utf-8")
    page = template.replace("/* REVIEW_CSS */", css).replace("/* REVIEW_JS */", js)
    path.write_text(page.replace("REVIEW_PAYLOAD", payload), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Reopen or combine saved JSON reports without running a model."""
    from scripts.evaluate_mdf_interactions import CASES_PATH, load_cases, same_file

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases", type=Path, help="original fixture catalog for older reports"
    )
    parser.add_argument("--focus", help="open this case when the page loads")
    args = parser.parse_args(argv)
    try:
        if any(
            same_file(args.output, path)
            for path in [*args.reports, args.cases or CASES_PATH]
        ):
            parser.error(
                "the output must be different from the reports and fixture catalog"
            )
        reports = [json.loads(path.read_bytes()) for path in args.reports]
        if not any(report.get("review_context") for report in reports):
            catalog = load_cases(args.cases or CASES_PATH)
            reports[0]["review_context"] = legacy_context(
                reports[0], catalog, require_match=bool(args.cases)
            )
        write_review(args.output, reports, focus=args.focus)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"Could not build the review page: {error}", file=sys.stderr)
        return 2
    print(f"Review page: {args.output}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(API_DIR))
    raise SystemExit(main())
