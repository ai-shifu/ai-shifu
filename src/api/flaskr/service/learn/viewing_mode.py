from __future__ import annotations

from flaskr.service.learn.learn_dtos import ViewingModeDTO
from flaskr.util.prompt_loader import load_prompt_template

DEVICE_TYPE_LABELS = {
    "mobile": "移动端",
    "desktop": "桌面端",
}


def build_viewing_mode_prompt(viewing_mode: ViewingModeDTO | None) -> str | None:
    if viewing_mode is None:
        return None

    template = load_prompt_template("view")
    device_label = DEVICE_TYPE_LABELS[viewing_mode.device_type]
    return template.format(
        container_size=viewing_mode.container_size,
        device_type=device_label,
    ).strip()
