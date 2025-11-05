from flask import Flask
from flaskr.util.uuid import generate_id
from flaskr.service.learn.models import LearnGeneratedBlock
from flaskr.service.shifu.shifu_struct_manager import get_shifu_struct, HistoryItem
from flaskr.service.shifu.models import PublishedOutlineItem, DraftOutlineItem
from flaskr.service.shifu.models import PublishedShifu, DraftShifu
from flaskr.service.shifu.consts import ASK_MODE_DEFAULT, ASK_MODE_DISABLE
from ...service.profile.funcs import get_user_profiles
import re
from typing import Union
from flaskr.service.shifu.struct_utils import find_node_with_parents


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


def init_generated_block(
    app: Flask,
    shifu_bid: str,
    outline_item_bid: str,
    progress_record_bid: str,
    user_bid: str,
    block_type: int,
    mdflow: str,
    block_index: int,
) -> LearnGeneratedBlock:
    generated_block: LearnGeneratedBlock = LearnGeneratedBlock()
    generated_block.progress_record_bid = progress_record_bid
    generated_block.user_bid = user_bid
    generated_block.outline_item_bid = outline_item_bid
    generated_block.shifu_bid = shifu_bid
    generated_block.block_bid = ""
    generated_block.type = block_type
    generated_block.generated_block_bid = generate_id(app)
    generated_block.generated_content = ""
    generated_block.status = 1
    generated_block.block_content_conf = mdflow
    generated_block.position = block_index
    return generated_block


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


def get_follow_up_info_v2(
    app: Flask,
    shifu_bid: str,
    outline_item_bid: str,
    attend_id: str,
    is_preview: bool = False,
) -> FollowUpInfo:
    """
    Get follow up info.

    Args:
        app (Flask): The Flask application instance.
        shifu_bid (str): The shifu business ID.
        outline_item_bid (str): The outline item business ID.
        attend_id (str): The attendance ID.
        is_preview (bool, optional): Whether to retrieve the follow up info in preview mode.
            If True, retrieves data as it would appear in preview (unpublished) state; if False,
            retrieves data as it appears in the published state. Defaults to False.

    Returns:
        FollowUpInfo: The follow up information for the given parameters.
    """
    struct_info = get_shifu_struct(app, shifu_bid, is_preview)
    path = find_node_with_parents(struct_info, outline_item_bid)
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

    shifu_info: Union[PublishedShifu, DraftShifu] = (
        shifu_model.query.filter(
            shifu_model.shifu_bid == shifu_bid, shifu_model.deleted == 0
        )
        .order_by(shifu_model.id.desc())
        .first()
    )
    ask_model = shifu_info.ask_llm if shifu_info.ask_llm else shifu_info.llm

    for p in path:
        if p.type == "outline":
            outline_info = outline_infos_map.get(p.bid, None)
            if outline_info.ask_enabled_status != ASK_MODE_DEFAULT:
                return FollowUpInfo(
                    ask_model=outline_info.ask_llm
                    if outline_info.ask_llm
                    else ask_model,
                    ask_prompt=outline_info.ask_llm_system_prompt,
                    ask_history_count=10,
                    ask_limit_count=10,
                    model_args={"temperature": outline_info.ask_llm_temperature},
                    ask_mode=outline_info.ask_enabled_status,
                )

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
