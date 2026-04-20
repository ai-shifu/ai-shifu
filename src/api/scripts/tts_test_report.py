"""
Generate a full TTS provider test report (HTML with <audio> playback).

Requirements implemented:
1) Uses the unified top-level pipeline (segmentation, synthesis, concat, OSS upload).
2) Uploads the final audio to OSS and returns OSS URLs.
3) Tests each provider/model/voice with both Chinese and English texts and measures time.
4) Outputs a tabular report with model, voice, language, synthesis time, and playable audio.
5) Embeds OSS URLs as <audio> players instead of download links.
"""

from __future__ import annotations

import argparse
import html
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# Ensure `/app` (repo root for src/api) is on sys.path when executed as a file path.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

# Avoid side-effectful app auto-creation on import.
os.environ.setdefault("SKIP_APP_AUTOCREATE", "1")

from app import create_app  # noqa: E402

from flaskr.api.tts import get_tts_provider  # noqa: E402


ZH_TEXT = """在辅导过几十家企业、上万人用 AI 提升业绩、效率之后，我总结出这三种观点是多数人都会有的对 AI 的误解：

观点一：AI 是一种工具
观点二：每种 AI 产品都需要学习使用方法
观点三：打造 AI 产品是技术高手的事情

你选择了都不同意，这个回答很棒！可以看出你有着超越常人的见解和判断力。

既然你对这些常见误解都有清醒的认识，那么这门《跟 AI 学 AI 通识》课程整体上可能对你的帮助不会太大。不过，其中某些地方可能还是会有一些启发性的观点，你可以根据需要决定是否继续学习。

但不管怎样，既然你已经来了，我还是想盛情邀请你继续学习下去。因为我深知，真正理解 AI 通识的人，在这个变革时代会拥有怎样的优势和机会。

让我简单自我介绍一下：我是 AI 师傅的创始人，曾是哈尔滨工业大学的副教授，后来在网易和得到 App 工作过。我的工作领域主要是互联网、人工智能和教育的结合，已经帮助各行各业的几万人转型成 AI 专业人士，还帮助数十家企业成功落地 AI 到生产实践。

你知道吗？在 ChatGPT 问世的第 6 天，我就注册并被深深震撼了。在深入了解这个技术变革之后，我给自己定了一个目标：帮助 100 万人顺利走进 AGI 时代

在实现这个目标的过程中，我慢慢发现，用好 AI 的前提是用户需要知道如何调教 AI，发挥 AI 的长处，弥补 AI 的短处。调教好了，可以一句话就让 AI 帮你完成繁琐的工作。

这门课就是专门讲如何调教 AI 的，帮你成为 AI 的主人。而且，调教的思路非常符合人的直觉，最核心的只需要理解三件事："""


EN_TEXT = """I appreciate your insight in disagreeing with all three misconceptions! Your critical thinking shows real promise. Given your current understanding, this course might offer limited comprehensive help, but there could be some valuable insights in specific areas. Feel free to decide whether to continue based on your needs.

Let me introduce myself - I'm the founder of AI-Shifu, a former associate professor at Harbin Institute of Technology, and I've worked at both NetEase and Dedao App. My work focuses on the intersection of internet, artificial intelligence, and education. I've helped tens of thousands of people across various industries transition to AI professionals, and assisted dozens of enterprises in successfully implementing AI into production practices.

On the 6th day after ChatGPT's release, I registered and was deeply shocked. After deeply understanding this technological transformation, I set myself a goal: help 1 million people smoothly enter the AGI era.

In the process of achieving this goal, I discovered that the premise of using AI well is that users need to know how to train AI, leverage AI's strengths, and compensate for AI's weaknesses. When properly trained, AI can complete tedious work with just one sentence.

This course teaches how to train AI, helping you become the master of AI. Moreover, the training approach aligns very intuitively with human thinking. The core understanding requires only three key concepts:"""


@dataclass(frozen=True)
class ReportRow:
    provider: str
    model: str
    voice_id: str
    voice_label: str
    language: str
    elapsed_seconds: float
    audio_url: str
    segment_count: int
    duration_ms: int
    error: str = ""

    def to_html_audio(self) -> str:
        if not self.audio_url:
            return ""
        url = html.escape(self.audio_url, quote=True)
        return f'<audio controls preload="none" src="{url}"></audio>'


def _safe_str(value: Any) -> str:
    return ("" if value is None else str(value)).strip()


def _build_cases(*, provider_name: str, matrix: str) -> list[dict[str, str]]:
    """
    Build test cases for a provider.

    matrix="coverage":
      - test all models (each with 1 representative voice)
      - test all voices (each with its compatible model / default model)

    matrix="full":
      - full cross-product for providers where that makes sense
    """
    provider = get_tts_provider(provider_name)
    cfg = provider.get_provider_config()

    models = list(cfg.models or [])
    voices = list(cfg.voices or [])

    # Default selections from provider config.
    default_voice_id = provider.get_default_voice_settings().voice_id
    default_model = _safe_str(models[0]["value"]) if models else ""

    voice_by_id = {v.get("value"): v for v in voices if v.get("value")}

    cases: list[dict[str, str]] = []

    def add_case(model_value: str, voice_value: str):
        cases.append(
            {
                "provider": provider_name,
                "model": _safe_str(model_value),
                "voice_id": _safe_str(voice_value),
                "voice_label": _safe_str(voice_by_id.get(voice_value, {}).get("label")),
            }
        )

    # Providers without models: just test voices.
    if not models:
        for voice in voices:
            add_case("", _safe_str(voice.get("value")))
        return cases

    if matrix == "full":
        # Full cross-product. For Volcengine, respect resource_id->voice mapping.
        if provider_name == "volcengine":
            for model in models:
                model_value = _safe_str(model.get("value"))
                for voice in voices:
                    if _safe_str(voice.get("resource_id")) != model_value:
                        continue
                    add_case(model_value, _safe_str(voice.get("value")))
        else:
            for model in models:
                model_value = _safe_str(model.get("value"))
                for voice in voices:
                    add_case(model_value, _safe_str(voice.get("value")))
        return cases

    # matrix == "coverage"
    # 1) Test each model with a representative voice.
    for model in models:
        model_value = _safe_str(model.get("value"))
        if provider_name == "volcengine":
            representative = next(
                (
                    _safe_str(v.get("value"))
                    for v in voices
                    if _safe_str(v.get("resource_id")) == model_value
                ),
                "",
            )
            if representative:
                add_case(model_value, representative)
        else:
            # Use provider default voice when possible, otherwise first voice.
            rep = default_voice_id if default_voice_id in voice_by_id else ""
            rep = rep or _safe_str(voices[0].get("value")) if voices else ""
            if rep:
                add_case(model_value, rep)

    # 2) Test each voice with a compatible/default model.
    for voice in voices:
        voice_value = _safe_str(voice.get("value"))
        if not voice_value:
            continue
        if provider_name == "volcengine":
            add_case(_safe_str(voice.get("resource_id")), voice_value)
        else:
            add_case(default_model, voice_value)

    # Deduplicate cases by (provider, model, voice)
    dedup: dict[tuple[str, str, str], dict[str, str]] = {}
    for case in cases:
        key = (case["provider"], case["model"], case["voice_id"])
        dedup[key] = case

    return list(dedup.values())


def _render_html(rows: list[ReportRow], *, output_path: str) -> str:
    success = sum(1 for row in rows if row.audio_url and not row.error)
    failed = len(rows) - success

    tr_rows = []
    for row in rows:
        tr_rows.append(
            "<tr>"
            f"<td>{html.escape(row.provider)}</td>"
            f"<td>{html.escape(row.model)}</td>"
            f"<td>{html.escape(row.voice_id)}</td>"
            f"<td>{html.escape(row.voice_label)}</td>"
            f"<td>{html.escape(row.language)}</td>"
            f"<td>{row.segment_count}</td>"
            f"<td>{row.duration_ms}</td>"
            f"<td>{row.elapsed_seconds:.3f}</td>"
            f"<td>{row.to_html_audio()}</td>"
            f"<td style='color:#b91c1c'>{html.escape(row.error)}</td>"
            "</tr>"
        )

    html_body = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>TTS Test Report</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border: 1px solid #e5e7eb; padding: 8px; vertical-align: top; }}
      th {{ background: #f9fafb; text-align: left; }}
      audio {{ width: 280px; }}
      .muted {{ color: #6b7280; font-size: 12px; }}
    </style>
  </head>
  <body>
    <h1>TTS Test Report</h1>
    <p class="muted">Rows: {len(rows)} | Success: {success} | Failed: {failed}</p>
    <table>
      <thead>
        <tr>
          <th>Provider</th>
          <th>Model</th>
          <th>Voice</th>
          <th>Voice Label</th>
          <th>Language</th>
          <th>Segments</th>
          <th>Audio Duration (ms)</th>
          <th>Synthesis Time (s)</th>
          <th>Preview</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {"".join(tr_rows)}
      </tbody>
    </table>
  </body>
</html>
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_body, encoding="utf-8")
    return str(out.resolve())


def _escape_markdown_cell(value: Any) -> str:
    cell = _safe_str(value)
    if not cell:
        return ""
    # Avoid breaking Markdown tables.
    cell = cell.replace("|", "\\|")
    # Render newlines as <br> so the table stays intact.
    cell = cell.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return cell


def _render_markdown(rows: list[ReportRow], *, output_path: str) -> str:
    success = sum(1 for row in rows if row.audio_url and not row.error)
    failed = len(rows) - success

    lines: list[str] = []
    lines.append("# TTS Test Report")
    lines.append("")
    lines.append(f"- Rows: {len(rows)}")
    lines.append(f"- Success: {success}")
    lines.append(f"- Failed: {failed}")
    lines.append("")
    lines.append(
        "| Provider | Model | Voice | Voice Label | Language | Segments | Audio Duration (ms) | Synthesis Time (s) | Preview | Error |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---:|---|---|")

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(row.provider),
                    _escape_markdown_cell(row.model),
                    _escape_markdown_cell(row.voice_id),
                    _escape_markdown_cell(row.voice_label),
                    _escape_markdown_cell(row.language),
                    str(int(row.segment_count)),
                    str(int(row.duration_ms)),
                    f"{row.elapsed_seconds:.3f}",
                    row.to_html_audio() or "",
                    _escape_markdown_cell(row.error),
                ]
            )
            + " |"
        )

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out.resolve())


def main():
    parser = argparse.ArgumentParser(description="Generate TTS provider HTML report")
    parser.add_argument(
        "--output",
        default="tmp/tts-test-report.html",
        help="Output HTML path (relative to /app when running in Docker)",
    )
    parser.add_argument(
        "--format",
        choices=("html", "markdown"),
        default="html",
        help="Report format (markdown embeds <audio> tags in table cells)",
    )
    parser.add_argument(
        "--providers",
        default="minimax,volcengine,aliyun,baidu",
        help="Comma-separated provider list",
    )
    parser.add_argument(
        "--matrix",
        choices=("coverage", "full"),
        default="coverage",
        help="Test matrix size (coverage is recommended; full can be expensive)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Max concurrent segment syntheses per case",
    )
    parser.add_argument(
        "--sleep-between-segments",
        type=float,
        default=0.0,
        help="Sleep seconds between segment syntheses (only applies when --max-workers=1)",
    )
    parser.add_argument(
        "--sleep-between-rows",
        type=float,
        default=0.0,
        help="Sleep seconds between each (provider,model,voice,language) row",
    )
    parser.add_argument(
        "--max-segment-chars",
        type=int,
        default=0,
        help="Override TTS_MAX_SEGMENT_CHARS (0 means use config default)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of (provider,model,voice,language) test rows (0 means no limit)",
    )
    args = parser.parse_args()

    app = create_app()
    # Reduce noisy logs and avoid leaking config values (keys/tokens) into stdout.
    logging.getLogger().setLevel(logging.ERROR)
    app.logger.setLevel(logging.ERROR)

    # Import after app initialization because some modules require an initialized DB.
    from flaskr.service.tts.pipeline import synthesize_long_text_to_oss  # noqa: E402
    from flaskr.service.tts.pipeline import SynthesizeToOssResult  # noqa: E402

    provider_names = [p.strip() for p in args.providers.split(",") if p.strip()]
    languages = [("zh", ZH_TEXT), ("en", EN_TEXT)]

    cases: list[dict[str, str]] = []
    for provider_name in provider_names:
        provider = get_tts_provider(provider_name)
        if not provider.is_configured():
            # Still produce rows (as failures) so the report is complete.
            cfg = provider.get_provider_config()
            if cfg.models:
                for model in cfg.models:
                    cases.append(
                        {
                            "provider": provider_name,
                            "model": _safe_str(model.get("value")),
                            "voice_id": provider.get_default_voice_settings().voice_id,
                            "voice_label": "",
                        }
                    )
            else:
                for voice in cfg.voices:
                    cases.append(
                        {
                            "provider": provider_name,
                            "model": "",
                            "voice_id": _safe_str(voice.get("value")),
                            "voice_label": _safe_str(voice.get("label")),
                        }
                    )
            continue

        cases.extend(_build_cases(provider_name=provider_name, matrix=args.matrix))

    rows: list[ReportRow] = []

    start_all = time.monotonic()
    for case in cases:
        for lang, text in languages:
            if args.limit and len(rows) >= args.limit:
                break

            provider_name = case["provider"]
            model = case["model"]
            voice_id = case["voice_id"]
            voice_label = case.get("voice_label", "")

            try:
                result: Optional[SynthesizeToOssResult] = None
                elapsed = 0.0
                t0 = time.monotonic()
                result = synthesize_long_text_to_oss(
                    app,
                    text=text,
                    provider_name=provider_name,
                    model=model,
                    voice_id=voice_id,
                    language=lang,
                    max_segment_chars=args.max_segment_chars or None,
                    max_workers=args.max_workers,
                    sleep_between_segments=args.sleep_between_segments,
                )
                elapsed = time.monotonic() - t0
                rows.append(
                    ReportRow(
                        provider=provider_name,
                        model=result.model,
                        voice_id=result.voice_id,
                        voice_label=voice_label,
                        language=lang,
                        elapsed_seconds=elapsed,
                        audio_url=result.audio_url,
                        segment_count=result.segment_count,
                        duration_ms=result.duration_ms,
                        error="",
                    )
                )
            except Exception as exc:
                rows.append(
                    ReportRow(
                        provider=provider_name,
                        model=model or "default",
                        voice_id=voice_id,
                        voice_label=voice_label,
                        language=lang,
                        elapsed_seconds=0.0,
                        audio_url="",
                        segment_count=0,
                        duration_ms=0,
                        error=str(exc),
                    )
                )
            finally:
                if args.sleep_between_rows:
                    time.sleep(args.sleep_between_rows)

        if args.limit and len(rows) >= args.limit:
            break

    elapsed_all = time.monotonic() - start_all
    if args.format == "markdown":
        output = _render_markdown(rows, output_path=args.output)
    else:
        output = _render_html(rows, output_path=args.output)
    print(f"Report written: {output}")
    print(f"Elapsed: {elapsed_all:.1f}s | Rows: {len(rows)}")


if __name__ == "__main__":
    main()
