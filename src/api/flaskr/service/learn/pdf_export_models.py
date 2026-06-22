from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class PdfExportWatermark:
    brand_name: str
    course_name: str
    lesson_name: str


@dataclass(slots=True, frozen=True)
class PdfExportInteractionButton:
    label: str
    value: str
    selected: bool = False


@dataclass(slots=True, frozen=True)
class PdfExportInteraction:
    interaction_type: str
    buttons: list[PdfExportInteractionButton] = field(default_factory=list)
    input_placeholder: str = ""
    input_value: str = ""
    is_multi_select: bool = False


@dataclass(slots=True, frozen=True)
class PdfExportBlock:
    block_type: str
    content: str
    order: int
    label: str = ""
    is_follow_up: bool = False
    interaction: PdfExportInteraction | None = None


@dataclass(slots=True, frozen=True)
class PdfExportDocument:
    course_bid: str
    lesson_bid: str
    course_name: str
    lesson_name: str
    preview_mode: bool
    watermark: PdfExportWatermark
    blocks: list[PdfExportBlock] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class PdfExportResult:
    file_path: str
    download_name: str
    temp_dir: str
