from flaskr.common.swagger import register_schema_to_swagger
import json
from flaskr.service.common.aidtos import AIDto


@register_schema_to_swagger
class ColorSetting:
    color: str  # the background color of the profile item
    text_color: str  # the text color of the profile item

    def __init__(self, color: str, text_color: str):
        self.color = color
        self.text_color = text_color

    def __json__(self):
        return {"color": self.color, "text_color": self.text_color}

    def __str__(self):
        return json.dumps(self.__json__(), ensure_ascii=True)


@register_schema_to_swagger
class ProfileItemDefinition:
    profile_key: str  # the key of the profile item and could be used in prompt
    color_setting: ColorSetting  # the color setting of the profile item
    profile_type: str  # the type of the profile item, could be text or option
    profile_remark: str  # the remark of the profile item
    profile_scope: str  # the scope of the profile item, could be system or user
    profile_scope_str: str  # the string of the profile scope,could be in i18n
    profile_id: str  # the id of the profile item

    def __init__(
        self,
        profile_key: str,
        color_setting: ColorSetting,
        profile_type: str,
        profile_type_str: str,
        profile_remark: str,
        profile_scope: str,
        profile_scope_str: str,
        profile_id: str,
    ):
        self.profile_key = profile_key
        self.color_setting = color_setting
        self.profile_type = profile_type
        self.profile_type_str = profile_type_str
        self.profile_remark = profile_remark
        self.profile_scope = profile_scope
        self.profile_scope_str = profile_scope_str
        self.profile_id = profile_id

    def __json__(self):
        return {
            "profile_key": self.profile_key,
            "color_setting": self.color_setting,
            "profile_type": self.profile_type,
            "profile_type_str": self.profile_type_str,
            "profile_remark": self.profile_remark,
            "profile_scope": self.profile_scope,
            "profile_scope_str": self.profile_scope_str,
            "profile_id": self.profile_id,
        }

    def __str__(self):
        return str(self.__json__())


DEFAULT_COLOR_SETTINGS = [
    ColorSetting(color="#FECACA", text_color="#DC2626"),  # red
    ColorSetting(color="#EA580C", text_color="#EA580C"),  # orange
    ColorSetting(color="#FEF08A", text_color="#CA8A04"),  # yellow
    ColorSetting(color="#BBF7D0", text_color="#22C55E"),  # green
    ColorSetting(color="#A5F3FC", text_color="#A5F3FC"),  # cyan
    ColorSetting(color="#BFDBFE", text_color="#2563EB"),  # blue
    ColorSetting(color="#DB2777", text_color="#DB2777"),  # pink
    ColorSetting(color="#FDE68A", text_color="#D97706"),  # amber
    ColorSetting(color="#D9F99D", text_color="#65A30D"),  # lime
    ColorSetting(color="#0D9488", text_color="#0D9488"),  # teal
    ColorSetting(color="#0284C7", text_color="#BAE6FD"),  # sky
    ColorSetting(color="#4F46E5", text_color="#C7D2FE"),  # indigo
]


@register_schema_to_swagger
class ProfileValueDto:
    name: str
    value: str

    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value

    def __json__(self):
        return {"name": self.name, "value": self.value}


@register_schema_to_swagger
class ProfileItemDto:
    profile_id: str
    profile_key: str
    profile_value: str
    profile_type: int

    def __init__(
        self, profile_id: str, profile_key: str, profile_value: str, profile_type: int
    ):
        self.profile_id = profile_id
        self.profile_key = profile_key
        self.profile_value = profile_value
        self.profile_type = profile_type

    def __json__(self):
        return {
            "profile_id": self.profile_id,
            "profile_key": self.profile_key,
            "profile_value": self.profile_value,
            "profile_type": self.profile_type,
        }


@register_schema_to_swagger
class TextProfileDto:
    profile_key: str
    profile_value: str
    profile_prompt: AIDto
    profile_intro: str

    def __init__(
        self,
        profile_key: str,
        profile_value: str,
        profile_prompt: AIDto,
        profile_intro: str,
    ):
        self.profile_key = profile_key
        self.profile_value = profile_value
        self.profile_prompt = profile_prompt
        self.profile_intro = profile_intro

    def __json__(self):
        return {
            "profile_key": self.profile_key,
            "profile_value": self.profile_value,
            "profile_prompt": self.profile_prompt,
            "profile_intro": self.profile_intro,
        }

    def __str__(self):
        return str(self.__json__())


@register_schema_to_swagger
class SelectProfileDto:
    profile_key: str
    profile_value: str
    profile_options: list[ProfileValueDto]

    def __init__(
        self,
        profile_key: str,
        profile_value: str,
        profile_options: list[ProfileValueDto],
    ):
        self.profile_key = profile_key
        self.profile_value = profile_value
        self.profile_options = profile_options

    def __json__(self):
        return {
            "profile_key": self.profile_key,
            "profile_value": self.profile_value,
            "profile_options": self.profile_options,
        }

    def __str__(self):
        return str(self.__json__())
