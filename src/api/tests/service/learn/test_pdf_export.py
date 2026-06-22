from __future__ import annotations

import time
from pathlib import Path

import pytest


def _require_app(app):
    if app is None:
        pytest.skip("App fixture disabled")


def test_filter_exportable_elements_preserves_order_and_follow_up_labels():
    from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
    from flaskr.service.learn.pdf_export import filter_exportable_elements

    elements = [
        ElementDTO(
            element_bid="element-1",
            generated_block_bid="block-1",
            element_index=1,
            role="teacher",
            element_type=ElementType.TEXT,
            element_type_code=1,
            content="正文内容",
        ),
        ElementDTO(
            element_bid="element-2",
            generated_block_bid="block-2",
            element_index=2,
            role="student",
            element_type=ElementType.ASK,
            element_type_code=206,
            content="追问问题",
        ),
        ElementDTO(
            element_bid="element-3",
            generated_block_bid="block-3",
            element_index=3,
            role="teacher",
            element_type=ElementType.ANSWER,
            element_type_code=214,
            content="追问回答",
        ),
    ]

    blocks = filter_exportable_elements(elements)

    assert [block.content for block in blocks] == ["正文内容", "追问问题", "追问回答"]
    assert [block.label for block in blocks] == ["", "追问", "追问回答"]
    assert [block.is_follow_up for block in blocks] == [False, True, True]


def test_filter_exportable_elements_keeps_historical_readable_content_flags():
    from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
    from flaskr.service.learn.learn_dtos import ElementPayloadDTO
    from flaskr.service.learn.pdf_export import filter_exportable_elements

    elements = [
        ElementDTO(
            element_bid="element-1",
            generated_block_bid="block-1",
            element_index=1,
            role="teacher",
            element_type=ElementType.TITLE,
            element_type_code=1,
            content="# 春节文化之旅",
            is_renderable=True,
            is_marker=True,
        ),
        ElementDTO(
            element_bid="element-2",
            generated_block_bid="block-2",
            element_index=2,
            role="teacher",
            element_type=ElementType.TEXT,
            element_type_code=1,
            content="欢迎来到春节文化之旅",
            is_renderable=False,
            is_marker=False,
        ),
        ElementDTO(
            element_bid="element-3",
            generated_block_bid="block-3",
            element_index=3,
            role="teacher",
            element_type=ElementType.HTML,
            element_type_code=1,
            content="<div>图文块</div>",
            is_renderable=True,
            is_marker=True,
        ),
        ElementDTO(
            element_bid="element-4",
            generated_block_bid="block-4",
            element_index=4,
            role="teacher",
            element_type=ElementType.INTERACTION,
            element_type_code=1,
            content="?[%{{choice}} A | B]",
            is_renderable=False,
            is_marker=True,
            payload=ElementPayloadDTO(user_input="A"),
        ),
    ]

    blocks = filter_exportable_elements(elements)

    assert [block.block_type for block in blocks] == [
        "title",
        "text",
        "html",
        "interaction",
    ]
    assert [block.content for block in blocks] == [
        "春节文化之旅",
        "欢迎来到春节文化之旅",
        "<div>图文块</div>",
        "?[%{{choice}} A | B]",
    ]
    assert blocks[-1].interaction is not None
    assert blocks[-1].interaction.buttons[0].selected is True
    assert blocks[-1].interaction.buttons[1].selected is False


def test_render_pdf_html_contains_watermark_and_follow_up_label():
    from flaskr.service.learn.pdf_export import (
        PDF_EXPORT_INTERACTION_SELECTED_LABEL,
        render_pdf_html,
    )
    from flaskr.service.learn.pdf_export_models import (
        PdfExportBlock,
        PdfExportDocument,
        PdfExportInteraction,
        PdfExportInteractionButton,
        PdfExportWatermark,
    )

    document = PdfExportDocument(
        course_bid="course-1",
        lesson_bid="lesson-1",
        course_name="课程A",
        lesson_name="第1节",
        preview_mode=False,
        watermark=PdfExportWatermark(
            brand_name="AI师傅",
            course_name="课程A",
            lesson_name="第1节",
        ),
        blocks=[
            PdfExportBlock(block_type="text", content="正文", order=0),
            PdfExportBlock(
                block_type="ask",
                content="追问问题",
                order=1,
                label="追问",
                is_follow_up=True,
            ),
            PdfExportBlock(
                block_type="interaction",
                content="?[%{{choice}} A | B]",
                order=2,
                interaction=PdfExportInteraction(
                    interaction_type="buttons_only",
                    buttons=[
                        PdfExportInteractionButton(
                            label="A",
                            value="A",
                            selected=True,
                        ),
                        PdfExportInteractionButton(
                            label="B",
                            value="B",
                            selected=False,
                        ),
                    ],
                ),
            ),
        ],
    )

    html = render_pdf_html(document)

    assert "AI师傅 / 课程A / 第1节" in html
    assert "追问" in html
    assert "追问问题" in html
    assert "block-follow-up-question" in html
    assert PDF_EXPORT_INTERACTION_SELECTED_LABEL in html
    assert "interaction-option-status" in html


def test_render_pdf_html_contains_text_interaction_input_value():
    from flaskr.service.learn.pdf_export import render_pdf_html
    from flaskr.service.learn.pdf_export_models import (
        PdfExportBlock,
        PdfExportDocument,
        PdfExportInteraction,
        PdfExportWatermark,
    )

    document = PdfExportDocument(
        course_bid="course-1",
        lesson_bid="lesson-1",
        course_name="课程A",
        lesson_name="第1节",
        preview_mode=False,
        watermark=PdfExportWatermark(
            brand_name="AI师傅",
            course_name="课程A",
            lesson_name="第1节",
        ),
        blocks=[
            PdfExportBlock(
                block_type="interaction",
                content="?[%{{idea}}...请输入]",
                order=0,
                interaction=PdfExportInteraction(
                    interaction_type="text_only",
                    input_placeholder="请输入",
                    input_value="美少女大战哥斯拉",
                ),
            ),
        ],
    )

    html = render_pdf_html(document)

    assert "美少女大战哥斯拉" in html
    assert "interaction-input-shell" in html


def test_filter_exportable_elements_normalizes_interaction_type_enum_text_only():
    from enum import Enum

    from flaskr.service.learn.learn_dtos import (
        ElementDTO,
        ElementPayloadDTO,
        ElementType,
    )
    from flaskr.service.learn.pdf_export import (
        filter_exportable_elements,
        render_pdf_html,
    )
    from flaskr.service.learn.pdf_export_models import (
        PdfExportDocument,
        PdfExportWatermark,
    )

    class _InteractionType(Enum):
        TEXT_ONLY = "text_only"

    elements = [
        ElementDTO(
            element_bid="element-1",
            generated_block_bid="block-1",
            element_index=1,
            role="teacher",
            element_type=ElementType.INTERACTION,
            element_type_code=1,
            content="?[%{{idea}}...请输入]",
            payload=ElementPayloadDTO(user_input="美少女大战哥斯拉"),
        )
    ]

    blocks = filter_exportable_elements(elements)
    interaction = blocks[0].interaction
    interaction = interaction.__class__(
        interaction_type=_InteractionType.TEXT_ONLY,
        buttons=interaction.buttons,
        input_placeholder=interaction.input_placeholder,
        input_value=interaction.input_value,
        is_multi_select=interaction.is_multi_select,
    )
    blocks[0] = blocks[0].__class__(
        block_type=blocks[0].block_type,
        content=blocks[0].content,
        order=blocks[0].order,
        label=blocks[0].label,
        is_follow_up=blocks[0].is_follow_up,
        interaction=interaction,
    )

    html = render_pdf_html(
        PdfExportDocument(
            course_bid="course-1",
            lesson_bid="lesson-1",
            course_name="课程A",
            lesson_name="第1节",
            preview_mode=False,
            watermark=PdfExportWatermark(
                brand_name="AI师傅",
                course_name="课程A",
                lesson_name="第1节",
            ),
            blocks=blocks,
        )
    )

    assert "互动输入" in html
    assert "互动选择" not in html
    assert "美少女大战哥斯拉" in html


def test_filter_exportable_elements_sanitizes_problematic_html_styles():
    from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
    from flaskr.service.learn.pdf_export import filter_exportable_elements

    elements = [
        ElementDTO(
            element_bid="element-1",
            generated_block_bid="block-1",
            element_index=1,
            role="teacher",
            element_type=ElementType.HTML,
            element_type_code=1,
            content=(
                '<div style="width:100%; min-height:100vh; overflow-y:auto; '
                'display:flex; align-items:center; justify-content:center;">内容</div>'
                '<div style="max-width:1200px; font-size:clamp(12px,calc(100vw/48),3vh)">视觉卡片</div>'
            ),
        )
    ]

    blocks = filter_exportable_elements(elements)

    assert "min-height" not in blocks[0].content
    assert "overflow-y" not in blocks[0].content
    assert "display:flex" not in blocks[0].content
    assert 'class="pdf-visual-card"' in blocks[0].content
    assert "max-width:680px" in blocks[0].content
    assert "font-size:14.17px" in blocks[0].content
    assert "内容" in blocks[0].content


def test_filter_exportable_elements_rasterizes_visual_html_when_temp_dir_available(
    tmp_path, monkeypatch
):
    from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
    from flaskr.service.learn.pdf_export import filter_exportable_elements

    def _fake_rasterize(content: str, *, order: int, temp_dir: str) -> str:
        return f'<img src="file://{temp_dir}/visual-card-{order}.png" />'

    monkeypatch.setattr(
        "flaskr.service.learn.pdf_export._rasterize_html_block_to_img_tag",
        _fake_rasterize,
    )

    elements = [
        ElementDTO(
            element_bid="element-1",
            generated_block_bid="block-1",
            element_index=1,
            role="teacher",
            element_type=ElementType.HTML,
            element_type_code=1,
            content=(
                '<div style="max-width:1200px; font-size:clamp(12px,calc(100vw/48),3vh); '
                'background:linear-gradient(135deg,#0F63EE 0%, #0F63EE 60%, rgba(15,99,238,0.2) 100%)">'
                "视觉卡片</div>"
            ),
        )
    ]

    blocks = filter_exportable_elements(elements, temp_dir=str(tmp_path))

    assert blocks[0].content.startswith('<img src="file://')


def test_build_pdf_file_name_sanitizes_reserved_characters():
    from flaskr.service.learn.pdf_export import build_pdf_file_name
    from flaskr.service.learn.pdf_export_models import (
        PdfExportDocument,
        PdfExportWatermark,
    )

    document = PdfExportDocument(
        course_bid="course-1",
        lesson_bid="lesson-1",
        course_name='课程/A:*?"<>|',
        lesson_name="第1节",
        preview_mode=False,
        watermark=PdfExportWatermark(
            brand_name="AI师傅",
            course_name="课程A",
            lesson_name="第1节",
        ),
        blocks=[],
    )

    file_name = build_pdf_file_name(document)

    assert file_name.endswith(".pdf")
    assert "/" not in file_name
    assert ":" not in file_name


def test_cleanup_expired_pdf_exports_removes_only_expired_dirs(app, tmp_path):
    _require_app(app)

    from flaskr.service.learn.pdf_export import cleanup_expired_pdf_exports

    root = tmp_path / "pdf-exports"
    root.mkdir(parents=True, exist_ok=True)
    expired_dir = root / "learn_pdf_export_expired"
    fresh_dir = root / "learn_pdf_export_fresh"
    expired_dir.mkdir()
    fresh_dir.mkdir()
    (expired_dir / "expired.pdf").write_text("expired", encoding="utf-8")
    (fresh_dir / "fresh.pdf").write_text("fresh", encoding="utf-8")

    now = time.time()
    old_timestamp = now - 10800 - 30
    fresh_timestamp = now - 60
    os_utime = __import__("os").utime
    os_utime(expired_dir, (old_timestamp, old_timestamp))
    os_utime(expired_dir / "expired.pdf", (old_timestamp, old_timestamp))
    os_utime(fresh_dir, (fresh_timestamp, fresh_timestamp))
    os_utime(fresh_dir / "fresh.pdf", (fresh_timestamp, fresh_timestamp))

    with app.app_context():
        app.config["PDF_EXPORT_TEMP_DIR"] = str(root)
        app.config["PDF_EXPORT_TTL_SECONDS"] = 10800
        result = cleanup_expired_pdf_exports(app)

    assert result["removed_dirs"] == 1
    assert result["removed_files"] == 1
    assert not expired_dir.exists()
    assert fresh_dir.exists()


def test_export_lesson_pdf_uses_system_temp_dir_and_generates_file(app, monkeypatch):
    _require_app(app)

    from flaskr.service.learn.learn_dtos import ElementDTO, ElementType
    from flaskr.service.learn.pdf_export import export_lesson_pdf
    from flaskr.service.learn.pdf_export_models import PdfExportResult

    class _Record:
        def __init__(self):
            self.elements = [
                ElementDTO(
                    element_bid="element-1",
                    generated_block_bid="block-1",
                    element_index=1,
                    role="teacher",
                    element_type=ElementType.TEXT,
                    element_type_code=1,
                    content="正文内容",
                )
            ]

    monkeypatch.setattr(
        "flaskr.service.learn.pdf_export.load_lesson_export_record",
        lambda *args, **kwargs: _Record(),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.pdf_export.get_shifu_info",
        lambda app, shifu_bid, preview_mode: type(
            "CourseInfo",
            (),
            {"title": "课程A"},
        )(),
    )
    monkeypatch.setattr(
        "flaskr.service.learn.pdf_export.resolve_lesson_title",
        lambda **kwargs: "第1节",
    )

    written = {}

    def _fake_generate_pdf_file(*, html: str, file_path: str) -> None:
        Path(file_path).write_text(html, encoding="utf-8")
        written["file_path"] = file_path

    monkeypatch.setattr(
        "flaskr.service.learn.pdf_export.generate_pdf_file",
        _fake_generate_pdf_file,
    )

    with app.app_context():
        result = export_lesson_pdf(
            app,
            shifu_bid="course-1",
            outline_bid="lesson-1",
            user_bid="user-1",
            preview_mode=False,
        )

    assert isinstance(result, PdfExportResult)
    assert result.download_name.endswith(".pdf")
    assert "learn_pdf_export_" in result.temp_dir
    assert Path(result.file_path).exists()
    assert Path(result.file_path).read_text(encoding="utf-8").find("正文内容") >= 0
