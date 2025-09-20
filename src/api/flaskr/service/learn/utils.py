import datetime
import json
import re
from typing import Union
from flaskr.service.common.models import raise_error
from flask import Flask
from flaskr.util.uuid import generate_id
from ...service.lesson.const import (
    ASK_MODE_DEFAULT,
    ASK_MODE_DISABLE,
)
from ...service.lesson.models import AICourse, AILesson, AILessonScript
from ...service.profile.funcs import get_user_profiles
from ...service.learn.dtos import ScriptDTO
from ...service.learn.models import LearnGeneratedBlock
from flaskr.service.user.models import User
from ...service.lesson.const import STATUS_PUBLISH, STATUS_DRAFT
from flaskr.i18n import get_current_language
from flaskr.service.shifu.dtos import LabelDTO
from flaskr.service.shifu.shifu_struct_manager import ShifuOutlineItemDto
from flaskr.service.shifu.adapter import BlockDTO
from flaskr.service.shifu.consts import BLOCK_TYPE_VALUES
from flaskr.service.shifu.shifu_struct_manager import get_shifu_struct
from flaskr.service.shifu.struct_utils import find_node_with_parents
from flaskr.service.shifu.models import (
    PublishedOutlineItem,
    PublishedShifu,
    DraftOutlineItem,
    DraftShifu,
)
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def generation_attend(
    app: Flask,
    user_info: User,
    attend_id: str,
    outline_item_info: ShifuOutlineItemDto,
    block_dto: BlockDTO,
    with_ui_conf: bool = False,
) -> LearnGeneratedBlock:
    """
    Generation attend
    the attend is used to store the attend info
    Args:
        app: Flask application instance
        user_info: User info
        attend_id: Attend id
        outline_item_info: Outline item info
        block_dto: Block dto
        with_ui_conf: With ui conf
    Returns:
        AICourseLessonAttendScript: Attend script
    """
    block_type = BLOCK_TYPE_VALUES.get(block_dto.type, None)
    if block_type is None:
        app.logger.error(f"Invalid block type: {block_dto.type}")
        block_type = 0
    generated_block: LearnGeneratedBlock = LearnGeneratedBlock()
    generated_block.progress_record_bid = attend_id
    generated_block.user_bid = user_info.user_id
    generated_block.outline_item_bid = outline_item_info.bid
    generated_block.shifu_bid = outline_item_info.shifu_bid
    generated_block.block_bid = block_dto.bid
    generated_block.type = block_type
    generated_block.generated_block_bid = generate_id(app)
    generated_block.generated_content = ""
    generated_block.status = 1
    if with_ui_conf:
        generated_block.block_content_conf = json.dumps(
            block_dto.block_content.__json__(), ensure_ascii=False
        )
    return generated_block


def check_phone_number(app, user_info: User, input):
    """
    Check phone number
    """
    if not re.match(r"^1[3-9]\d{9}$", input):
        return False
    return True


def fmt(o):
    if isinstance(o, datetime.datetime):
        return o.isoformat()
    else:
        return o.__json__()


def extract_json(app: Flask, text: str):
    stack = []
    start = None
    for i, char in enumerate(text):
        if char == "{":
            if not stack:
                start = i
            stack.append(char)
        elif char == "}":
            if stack:
                stack.pop()
                if not stack:
                    json_str = text[start : i + 1]  # noqa
                    try:
                        json_obj = json.loads(json_str)
                        return json_obj
                    except json.JSONDecodeError:
                        pass
    return {}


def extract_json_from_markdown(app: Flask, text: str):
    """
    Extract json from markdown
    """
    markdown_patterns = [
        r"```json\s*\n(.*?)\n```",  # ```json format
        r"```\s*\n(.*?)\n```",  # ``` format
    ]
    app.logger.info(f"extract_json_from_markdown: {text}")
    for pattern in markdown_patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            json_obj = extract_json(app, match.strip())
            if json_obj:
                return json_obj
    return extract_json(app, text)


def extract_variables(template: str) -> list:
    # Match all {xxx} or {{xxx}} in the template
    pattern = r"\{{1,2}([^{}]+)\}{1,2}"
    matches = re.findall(pattern, template)
    # Only keep valid variable names (letters, digits, underscore, hyphen), no dots, commas, colons, quotes, or spaces
    variables = [
        m.strip()
        for m in matches
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", m.strip())
    ]
    return list(set(variables))


def safe_format_template(template: str, variables: dict) -> str:
    """
    Safe format template
    """
    # Replace {xxx} or {{xxx}} with values from variables dict, keep original if not found
    pattern = re.compile(r"(\{{1,2})([^{}]+)(\}{1,2})")

    def replacer(match):
        left, var, right = match.groups()
        var_name = var.strip()
        # Only process variable names with letters, digits, underscore, hyphen
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_-]*", var_name):
            if var_name in variables:
                return str(variables[var_name])
        # Otherwise, keep the original
        return match.group(0)

    return pattern.sub(replacer, template)


def get_fmt_prompt(
    app: Flask,
    user_id: str,
    course_id: str,
    profile_tmplate: str,
    input: str = None,
    profile_array_str: str = None,
) -> str:
    """
    Get fmt prompt
    Args:
        app: Flask application instance
        user_id: User id
        course_id: Course id
        profile_tmplate: Profile template
        input: Input
        profile_array_str: Profile array str
    Returns:
        str: Fmt prompt
    """
    app.logger.info("raw prompt:" + profile_tmplate)
    propmpt_keys = []
    profiles = {}

    profiles = get_user_profiles(app, user_id, course_id)
    propmpt_keys = list(profiles.keys())
    if input:
        profiles["sys_user_input"] = input
        propmpt_keys.append("sys_user_input")
    app.logger.info(propmpt_keys)
    app.logger.info(profiles)
    keys = extract_variables(profile_tmplate)
    fmt_keys = {}
    for key in keys:
        if key in profiles:
            fmt_keys[key] = profiles[key]
        else:
            app.logger.info("key not found:" + key + " ,user_id:" + user_id)
    app.logger.info(fmt_keys)
    if not keys:
        prompt = input if not profile_tmplate else profile_tmplate
    else:
        prompt = safe_format_template(profile_tmplate, fmt_keys)
    app.logger.info("fomat input:{}".format(prompt))
    return prompt


def make_script_dto(
    script_type, script_content, script_id, lesson_id=None, log_id=None
) -> str:
    """
    Make script dto
    Args:
        script_type: Script type
        script_content: Script content
        script_id: Script id
        lesson_id: Lesson id
        log_id: Log id
    Returns:
        str: Script dto for stream
    """
    return (
        "data: "
        + json.dumps(
            ScriptDTO(script_type, script_content, lesson_id, script_id, log_id),
            default=fmt,
            ensure_ascii=False,
        )
        + "\n\n".encode("utf-8").decode("utf-8")
    )


def make_script_dto_to_stream(dto: ScriptDTO) -> str:
    """
    Make script dto to stream
    Args:
        dto: Script dto
    Returns:
        str: Script dto to stream
    """
    return (
        "data: "
        + json.dumps(dto, default=fmt, ensure_ascii=False)
        + "\n\n".encode("utf-8").decode("utf-8")
    )


class FollowUpInfo:
    """
    Follow up info
    """

    ask_model: str
    ask_prompt: str
    ask_history_count: int
    ask_limit_count: int
    model_args: dict
    ask_mode: int

    def __init__(
        self,
        ask_model,
        ask_prompt,
        ask_history_count,
        ask_limit_count,
        model_args,
        ask_mode,
    ):
        self.ask_model = ask_model
        self.ask_prompt = ask_prompt
        self.ask_history_count = ask_history_count
        self.ask_limit_count = ask_limit_count
        self.model_args = model_args
        self.ask_mode = ask_mode

    def __json__(self):
        return {
            "ask_model": self.ask_model,
            "ask_prompt": self.ask_prompt,
            "ask_history_count": self.ask_history_count,
            "ask_limit_count": self.ask_limit_count,
            "model_args": self.model_args,
            "ask_mode": self.ask_mode,
        }


def get_follow_up_info(
    app: Flask,
    shifu_bid: str,
    block_dto: BlockDTO,
    attend_id: str,
    is_preview: bool = False,
) -> FollowUpInfo:
    """
    Get follow up info.

    Args:
        app (Flask): The Flask application instance.
        shifu_bid (str): The shifu business ID.
        block_dto (BlockDTO): The block data transfer object.
        attend_id (str): The attendance ID.
        is_preview (bool, optional): Whether to retrieve the follow up info in preview mode.
            If True, retrieves data as it would appear in preview (unpublished) state; if False,
            retrieves data as it appears in the published state. Defaults to False.

    Returns:
        FollowUpInfo: The follow up information for the given parameters.
    """
    struct_info = get_shifu_struct(app, shifu_bid, is_preview)
    path = find_node_with_parents(struct_info, block_dto.bid)
    if not path:
        return FollowUpInfo(
            ask_model="",
            ask_prompt="",
            ask_history_count=10,
            ask_limit_count=10,
            model_args={"temperature": 0.0},
            ask_mode=ASK_MODE_DISABLE,
        )
    path = list(reversed(path))
    path: list[HistoryItem] = [p for p in path if p.type == "outline"]
    outline_ids = [p.id for p in path]
    outline_model = PublishedOutlineItem if not is_preview else DraftOutlineItem
    shifu_model = PublishedShifu if not is_preview else DraftShifu
    outline_infos: list[Union[PublishedOutlineItem, DraftOutlineItem]] = (
        outline_model.query.filter(
            outline_model.id.in_(outline_ids),
        ).all()
    )
    outline_infos_map: dict[str, Union[PublishedOutlineItem, DraftOutlineItem]] = {
        o.outline_item_bid: o for o in outline_infos
    }

    for p in path:
        if p.type == "outline":
            outline_info = outline_infos_map.get(p.bid, None)
            if outline_info.ask_enabled_status != ASK_MODE_DEFAULT:
                return FollowUpInfo(
                    ask_model=outline_info.ask_llm,
                    ask_prompt=outline_info.ask_llm_system_prompt,
                    ask_history_count=10,
                    ask_limit_count=10,
                    model_args={"temperature": outline_info.ask_llm_temperature},
                    ask_mode=outline_info.ask_enabled_status,
                )
    shifu_info: Union[PublishedShifu, DraftShifu] = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid, shifu_model.deleted == 0
        )
        .order_by(shifu_model.id.desc())
        .first()
    )
    ask_model = shifu_info.ask_llm
    ask_prompt = shifu_info.ask_llm_system_prompt
    ask_history_count = 10
    ask_limit_count = 10
    model_args = {"temperature": shifu_info.ask_llm_temperature}
    return FollowUpInfo(
        ask_model,
        ask_prompt,
        ask_history_count,
        ask_limit_count,
        model_args,
        shifu_info.ask_enabled_status,
    )


class ModelSetting:
    """
    Model setting
    """

    model_name: str
    model_args: dict

    def __init__(self, model_name: str, model_args: dict):
        self.model_name = model_name
        self.model_args = model_args

    def __json__(self):
        return {"model_name": self.model_name, "model_args": self.model_args}


def get_model_setting(
    app: Flask, script_info: AILessonScript, status: list[int] = None
) -> ModelSetting:
    """
    Get model setting
    """
    if status is None:
        status = [STATUS_PUBLISH, STATUS_DRAFT]
    if script_info.script_model and script_info.script_model.strip():
        return ModelSetting(
            script_info.script_model, {"temperature": script_info.script_temperature}
        )
    ai_lesson = (
        AILesson.query.filter(
            AILesson.lesson_id == script_info.lesson_id,
            AILesson.status.in_(status),
        )
        .order_by(AILesson.id.desc())
        .first()
    )
    if (
        ai_lesson
        and ai_lesson.lesson_default_model
        and ai_lesson.lesson_default_model.strip()
    ):
        return ModelSetting(
            ai_lesson.lesson_default_model,
            {"temperature": ai_lesson.lesson_default_temperature},
        )
    ai_course = (
        AICourse.query.filter(
            AICourse.course_id == ai_lesson.course_id,
            AICourse.status.in_(status),
        )
        .order_by(AICourse.id.desc())
        .first()
    )
    if (
        ai_course
        and ai_course.course_default_model
        and ai_course.course_default_model.strip()
    ):
        return ModelSetting(
            ai_course.course_default_model,
            {"temperature": ai_course.course_default_temperature},
        )
    default_model = app.config.get("DEFAULT_LLM_MODEL", "")
    if not default_model or default_model == "":
        raise_error("LLM.NO_DEFAULT_LLM")
    return ModelSetting(
        app.config.get("DEFAULT_LLM_MODEL"),
        {"temperature": float(app.config.get("DEFAULT_LLM_TEMPERATURE"))},
    )


def get_script_ui_label(app, text):
    """
    Get script ui label, used to display the script ui in the client
    Args:
        app: Flask application instance
        text: Text
    Returns:
        str: Script ui label
    """
    if isinstance(text, dict):
        label = text.get(get_current_language(), "")
        return label
    if text and isinstance(text, str) and text.strip().startswith("{"):
        try:
            json_obj = json.loads(text)
            label = json_obj.get(get_current_language(), "")
            if not label:
                if json_obj.values():
                    return list(json_obj.values())[0]
            return label
        except Exception:
            from flask import current_app

            current_app.logger.error(f"get_script_ui_label error: {text}")
            return text
    if text and isinstance(text, LabelDTO):
        label_dto: LabelDTO = text
        label = label_dto.lang.get(get_current_language(), "")
        if not label:
            if label_dto.lang.values():
                return list(label_dto.lang.values())[0]
        return label
    return text
