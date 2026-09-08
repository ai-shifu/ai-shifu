"""Build a portable, offline slide comparison page from verified local images."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
import tempfile
from pathlib import Path

from .state import ArenaError, artifact_id, private_directory, utc_now

TOOL_ROOT = Path(__file__).resolve().parents[1]
MAX_REPORT_IMAGE_BYTES = 64 * 1024 * 1024
MAX_REPORT_PAGES = 1000


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _image(path_value: str, hashes: dict, run_dir: Path, budget: dict) -> str:
    path = Path(path_value)
    if (
        not path.is_absolute()
        or not path.resolve().is_relative_to(run_dir.resolve())
        or path.suffix.lower() != ".png"
        or not path.is_file()
    ):
        message = "Report images must be PNG files inside the private run directory"
        raise ArenaError(message)
    message = "Report exceeds the aggregate image budget (64 MiB / 1000 pages); use a smaller batch"
    if budget["pages"] <= 0 or path.stat().st_size > budget["bytes"]:
        raise ArenaError(message)
    # Bound the read as well as stat: a file could grow between the two.
    with path.open("rb") as stream:
        data = stream.read(budget["bytes"] + 1)
    if len(data) > budget["bytes"]:
        raise ArenaError(message)
    budget["bytes"] -= len(data)
    budget["pages"] -= 1
    if hashes.get(path_value) != hashlib.sha256(data).hexdigest():
        message = "Report image bytes do not match the verified render"
        raise ArenaError(message)
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _number(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def performance(artifact: dict) -> dict:
    """Aggregate recorded calls only when every call supplies a valid metric."""
    metadata = artifact.get("metadata", {})
    requests = metadata.get("requests", [])

    def total(key: str, *, usage: bool = False) -> float | None:
        values = [
            (item.get("usage") or {}).get(key) if usage else item.get(key)
            for item in requests
        ]
        return (
            sum(values) if values and all(_number(value) for value in values) else None
        )

    elapsed = metadata.get("elapsed_ms")
    latency = total("latency_ms")
    output = total("output", usage=True)
    return {
        "elapsed": elapsed / 1000 if _number(elapsed) else None,
        "latency": latency / 1000 if latency is not None else None,
        "input": total("input", usage=True),
        "output": output,
        "cache": total("input_cache_tokens"),
        "speed": output * 1000 / latency if output is not None and latency else None,
    }


def _performance_html(artifact: dict, copy: dict) -> str:
    values = performance(artifact)
    fields = []
    for key, value in values.items():
        if value is None:
            formatted = copy["not_recorded"]
        elif key in {"elapsed", "latency"}:
            formatted = f"{value:,.1f} s"
        elif key == "speed":
            formatted = f"{value:,.1f} token/s"
        else:
            formatted = f"{value:,.0f}"
        fields.append(
            f"<div><dt>{_escape(copy['performance'][key])}</dt><dd>{_escape(formatted)}</dd></div>"
        )
    return '<dl class="performance">' + "".join(fields) + "</dl>"


def _cell(
    artifact: dict, copy: dict, run_dir: Path, budget: dict
) -> tuple[str, int, bool]:
    metrics = _performance_html(artifact, copy)
    status = artifact.get("status", "pending")
    markers = sum(
        item.get("is_marker") is True for item in artifact.get("elements", [])
    )
    if status == "complete" and not markers:
        status = "no_slides"
    render = artifact.get("render", {})
    pages = render.get("pages", [])
    if status == "complete" and (not pages or len(pages) < markers):
        status = "render_failed"
    if status != "complete":
        label = copy["statuses"].get(status, copy["statuses"]["pending"])
        return f'<td>{metrics}<p class="failure">{_escape(label)}</p></td>', 0, False
    images = []
    for index, page in enumerate(pages, 1):
        src = _image(page, render.get("sha256", {}), run_dir, budget)
        label = copy["page"].format(number=index, total=len(pages))
        images.append(
            f'<figure><button class="zoom" aria-label="{_escape(label)}">'
            f'<img loading="lazy" src="{src}" alt="{_escape(label)}"></button>'
            f"<figcaption>{_escape(label)}</figcaption></figure>"
        )
    return (
        f'<td>{metrics}<p class="metrics">{len(pages)} {_escape(copy["pages"])}</p>'
        + "".join(images)
        + "</td>",
        len(pages),
        True,
    )


def write_report(manifest: dict, run_dir: Path) -> dict:
    """Embed all slide pages in one HTML file, without remote reads or paid calls."""
    from markdown_flow import MarkdownFlow

    copy = json.loads((TOOL_ROOT / "i18n/zh-CN.json").read_text())
    cases = [case for case in manifest["cases"] if case.get("category") == "slides"]
    # Freeze display order by run and exact route, independently of call order.
    models = sorted(
        manifest["models"],
        key=lambda model: hashlib.sha256(
            f"{manifest.get('run_id', '')}:{model['model']}".encode()
        ).hexdigest(),
    )
    if not cases or not models:
        message = "No frozen slide cases and model routes are available for a report"
        raise ArenaError(message)
    budget = {"bytes": MAX_REPORT_IMAGE_BYTES, "pages": MAX_REPORT_PAGES}
    rows = []
    page_count = complete_count = 0
    for index, case in enumerate(cases, 1):
        source = case.get("source", {})
        title = source.get("outline_title") or case["case_id"]
        course = source.get("course_title", "")
        document = case.get("document", "")
        blocks = MarkdownFlow(document=document).get_all_blocks() if document else []
        block_index = case.get("block_index", 0)
        target = blocks[block_index].content if 0 <= block_index < len(blocks) else ""
        heading = (
            f'<tr class="case"><th colspan="{len(models)}" scope="rowgroup">'
            f'<span class="number">{index:02}</span> {_escape(title)}'
            f"<small>{_escape(course)}</small><details><summary>{_escape(copy['prompt'])}</summary>"
            f"<h3>{_escape(copy['target'])}</h3><pre>{_escape(target)}</pre>"
            f"<h3>{_escape(copy['inherited'])}</h3><pre>{_escape(case.get('document_prompt', ''))}</pre>"
            f"</details></th></tr>"
        )
        cells = []
        for model in models:
            artifact = manifest["artifacts"].get(artifact_id(case, model), {})
            cell, count, complete = _cell(artifact, copy, run_dir, budget)
            cells.append(cell)
            page_count += count
            complete_count += int(complete)
        rows.append(
            f'<tbody data-case="{_escape(case["case_id"])}">{heading}<tr>{"".join(cells)}</tr></tbody>'
        )
    headers = "".join(
        f'<th scope="col"><span class="model-code">{chr(65 + index)}</span>'
        f'<span class="model-name" hidden>{_escape(model["requested"])}'
        f"<small>{_escape(model['model'])}</small></span></th>"
        for index, model in enumerate(models)
    )
    css = (TOOL_ROOT / "report.css").read_text()
    script = (TOOL_ROOT / "report.js").read_text()
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    page = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        f"img-src data:; style-src 'unsafe-inline'; script-src 'sha256-{script_hash}'; "
        "base-uri 'none'; form-action 'none'\">"
        f"<title>{_escape(copy['title'])}</title><style>{css}</style></head><body>"
        f'<header><p class="eyebrow">MARKDOWNFLOW · MODEL COMPARISON</p><h1>{_escape(copy["title"])}</h1>'
        f'<p>{_escape(copy["intro"])}</p><p class="counts">{len(cases)} {_escape(copy["cases"])} · '
        f"{len(models)} {_escape(copy['models'])} · {page_count} {_escape(copy['pages'])}</p></header>"
        f'<main><table id="comparison" style="min-width:{len(models) * 300}px"><thead><tr>{headers}</tr></thead>{"".join(rows)}</table></main>'
        f"<footer><p>{_escape(copy['performance_note'])}</p>"
        f'<button id="reveal-models" aria-controls="comparison" aria-expanded="false" '
        f'data-revealed-label="{_escape(copy["revealed"])}">{_escape(copy["reveal"])}</button></footer>'
        f'<dialog><button class="close" autofocus>{_escape(copy["close"])}</button><img alt=""></dialog>'
        f"<script>{script}</script></body></html>"
    )
    private_directory(run_dir)
    descriptor, temporary = tempfile.mkstemp(prefix=".comparison-", dir=run_dir)
    output = run_dir / "comparison.html"
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(page)
        Path(temporary).replace(output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {
        "path": str(output.resolve()),
        "created_at": utc_now(),
        "case_count": len(cases),
        "model_count": len(models),
        "complete_count": complete_count,
        "page_count": page_count,
        "unavailable_count": len(cases) * len(models) - complete_count,
    }
