import logging
import os
import json
from enum import Enum
from typing import Optional, List

from dotenv import load_dotenv, find_dotenv
import streamlit as st

from tools.lark import get_bitable_records

_ = load_dotenv(find_dotenv())
LARK_APP_ID = os.environ.get("LARK_APP_ID")
LARK_APP_SECRET = os.environ.get("LARK_APP_SECRET")


class ScriptType(Enum):
    FIXED = "固定剧本"
    PROMPT = "Prompt"
    SYSTEM = "系统角色"


class ScriptFormat(Enum):
    MARKDOWN = "文本"
    IMAGE = "图片"
    NONE = "无"


class BtnFor(Enum):
    CONTINUE = "继续"


class NextAction(Enum):
    ShowInput = "显示 输入框"
    ShowBtn = "显示 按钮"
    ShowBtnGroup = "显示 按钮组"
    JumpBtn = "跳转按钮"
    ShowPayQR = "显示 付款码"
    InputPhoneNum = "输入 手机号"
    InputVerifyCode = "输入 验证码"
    ShowLoginReg = "显示 登录注册框"
    NoAction = "无"


class Script:
    """单条剧本"""

    def __init__(
        self,
        id,
        desc,
        type,
        format,
        template,
        template_vars,
        media_url,
        next_action,
        btn_label,
        btn_group_cfg,
        btn_jump_cfg,
        input_placeholder,
        check_template,
        check_ok_sign,
        parse_vars,
        custom_model,
        temperature,
    ):
        """剧本对象

        :param id: 【必填】在使用飞书多维表格时，填写其记录的ID
        :param desc: 【必填】剧本简述
        :param type: 【必填】剧本类型，可选值：ScriptType.FIXED, ScriptType.PROMPT
        :param format: 仅固定剧本时必填，可选值：ScriptFormat.MARKDOWN, ScriptFormat.IMAGE
        :param template: 【必填】剧本模版。 固定剧本时直接输出给用户；Prompt剧本时，将内容提交给AI，AI返回结果后输出
        :param template_vars: 模版变量，需要时提供变量名称列表
        :param media_url: 仅图片剧本时必填，图片地址
        :param next_action: 【必填】后续交互，可选值：NextAction.ShowInput, NextAction.ShowBtn, NextAction.NoAction
        :param btn_label: 后续交互为按钮时，按钮的标签
        :param btn_group_cfg: 后续交互为按钮组时，按钮组的配置
        :param btn_jump_cfg: 后续交互为跳转按钮时，跳转按钮的配置
        :param input_placeholder: 后续交互为输入时，输入框的提示语
        :param check_template: 后续交互为输入时，提供检查模版，用于检查用户输入是否符合要求
        :param check_ok_sign: 后续交互为输入时，检查通过的标志
        :param parse_vars: 后续交互为输入时，提供解析变量名列表，用于解析用户输入
        :param custom_model: 单条剧本指定使用自定义模型时，提供模型名称
        :param temperature: 单条剧本指定使用自定义温度时，提供温度值
        """

        self.id: str = id
        self.desc: str = desc
        self.type: ScriptType = type
        self.format: Optional[ScriptFormat] = format
        self.template: Optional[str] = template
        self.template_vars: Optional[List[str]] = template_vars
        self.media_url: Optional[str] = media_url
        self.next_action: NextAction = next_action
        self.btn_label: Optional[str] = btn_label
        self.btn_group_cfg: Optional[dict] = btn_group_cfg
        self.btn_jump_cfg: Optional[dict] = btn_jump_cfg
        self.input_placeholder: Optional[str] = input_placeholder
        self.check_template: Optional[str] = check_template
        self.check_ok_sign: Optional[str] = check_ok_sign
        self.parse_vars: Optional[List[str]] = parse_vars
        self.custom_model: Optional[str] = custom_model
        self.temperature: Optional[float] = temperature

    def __repr__(self):
        return f"{self.desc}"

    def __eq__(self, other):
        if isinstance(other, Script):
            return self.id == other.id
        return False


@st.cache_data(show_spinner="Load scripts from Lark's bitable...")
def load_scripts_from_bitable(app_token, table_id, view_id) -> List[Script]:
    logging.info(
        f"开始加载剧本记录：app_token={app_token}, table_id={table_id}, view_id={view_id}"
    )
    items = get_bitable_records(app_token, table_id, view_id)

    script_list = []
    for item in items:
        try:
            id = item.record_id
            if not item.fields:
                logging.warn(f"剧本记录为空，ID：{id}")
                continue

            desc = "".join(
                item["text"]
                for item in item.fields.get("剧本简述", [{"text": "未填写！"}])
            )
            script_type = ScriptType(item.fields.get("剧本类型", "固定剧本"))
            script_format = ScriptFormat(item.fields.get("内容格式", "文本"))
            template = "".join(
                item["text"]
                for item in item.fields.get("模版内容", [{"text": "未填写！"}])
            )
            template_vars = item.fields.get("模版变量")
            media_url = (
                item.fields.get("媒体URL")["text"]
                if item.fields.get("媒体URL")
                else None
            )
            next_action = NextAction(item.fields.get("后续交互", "无"))
            btn_label = "".join(
                item["text"] for item in item.fields.get("按钮标题", [{"text": "继续"}])
            )
            btn_group_cfg = json.loads(
                "".join(
                    item["text"]
                    for item in item.fields.get("按钮组配置", [{"text": "{}"}])
                )
            )
            btn_jump_cfg = json.loads(
                "".join(
                    item["text"]
                    for item in item.fields.get("跳转配置", [{"text": "{}"}])
                )
            )
            input_placeholder = "".join(
                item["text"]
                for item in item.fields.get("输入框提示", [{"text": "请输入"}])
            )
            check_template = "".join(
                item["text"]
                for item in item.fields.get("检查模版内容", [{"text": "未填写！"}])
            )
            check_ok_sign = "".join(
                item["text"]
                for item in item.fields.get("输入成功标识", [{"text": "OK"}])
            )
            parse_vars = item.fields.get("解析用户输入内容", None)
            custom_model = item.fields.get("自定义模型", None)
            temperature = item.fields.get("temperature", None)

            script_list.append(
                Script(
                    id,
                    desc,
                    script_type,
                    script_format,
                    template,
                    template_vars,
                    media_url,
                    next_action,
                    btn_label,
                    btn_group_cfg,
                    btn_jump_cfg,
                    input_placeholder,
                    check_template,
                    check_ok_sign,
                    parse_vars,
                    custom_model,
                    temperature,
                )
            )
        except Exception as e:
            logging.error(f"加载剧本记录失败，剧本ID：{id}")
            logging.error(f"剧本内容：{item.fields}")
            logging.error(f"异常信息：{e}")
            raise e

    return script_list
