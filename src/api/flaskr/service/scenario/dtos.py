from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class ScenarioDto:
    scenario_id: str
    scenario_name: str
    scenario_description: str
    scenario_image: str
    scenario_state: int
    is_favorite: bool

    def __init__(
        self,
        scenario_id: str,
        scenario_name: str,
        scenario_description: str,
        scenario_image: str,
        scenario_state: int,
        is_favorite: bool,
    ):
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.scenario_description = scenario_description
        self.scenario_image = scenario_image
        self.scenario_state = scenario_state
        self.is_favorite = is_favorite

    def __json__(self):
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description,
            "scenario_image": self.scenario_image,
            "scenario_state": self.scenario_state,
            "is_favorite": self.is_favorite,
        }


@register_schema_to_swagger
class ChapterDto:
    chapter_id: str
    chapter_name: str
    chapter_description: str
    chapter_type: int

    def __init__(
        self,
        chapter_id: str,
        chapter_name: str,
        chapter_description: str,
        chapter_type: int,
    ):
        self.chapter_id = chapter_id
        self.chapter_name = chapter_name
        self.chapter_description = chapter_description
        self.chapter_type = chapter_type

    def __json__(self):
        return {
            "chapter_id": self.chapter_id,
            "chapter_name": self.chapter_name,
            "chapter_description": self.chapter_description,
            "chapter_type": self.chapter_type,
        }


@register_schema_to_swagger
class SimpleOutlineDto:
    outline_id: str
    outline_no: str
    outline_name: str
    outline_children: list["SimpleOutlineDto"]

    def __init__(
        self,
        outline_id: str,
        outline_no: str,
        outline_name: str,
        outline_children: list["SimpleOutlineDto"] = None,
    ):
        self.outline_id = outline_id
        self.outline_no = outline_no
        self.outline_name = outline_name
        self.outline_children = outline_children if outline_children is not None else []

    def __json__(self):
        return {
            "outline_id": self.outline_id,
            "outline_no": self.outline_no,
            "outline_name": self.outline_name,
            "outline_children": self.outline_children,
        }


@register_schema_to_swagger
class UnitDto:
    unit_id: str
    unit_no: str
    unit_name: str


@register_schema_to_swagger
class OutlineDto:
    outline_id: str
    outline_no: str
    outline_name: str
    outline_desc: str
    outline_type: int

    def __init__(
        self,
        outline_id: str,
        outline_no: str,
        outline_name: str,
        outline_desc: str,
        outline_type: int,
    ):
        self.outline_id = outline_id
        self.outline_no = outline_no
        self.outline_name = outline_name
        self.outline_desc = outline_desc
        self.outline_type = outline_type

    def __json__(self):
        return {
            "outline_id": self.outline_id,
            "outline_no": self.outline_no,
            "outline_name": self.outline_name,
            "outline_desc": self.outline_desc,
            "outline_type": self.outline_type,
        }


# prompt
@register_schema_to_swagger
class AIDto:
    prompt: str
    profiles: str
    model: str
    temprature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        profiles: list[str] = None,
        model: str = None,
        temprature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.profiles = profiles
        self.model = model
        self.temprature = temprature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "profiles": self.profiles,
                "model": self.model,
                "temprature": self.temprature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


# prompt
@register_schema_to_swagger
class SystemPromptDto:
    prompt: str
    profiles: str
    model: str
    temprature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        profiles: list[str] = None,
        model: str = None,
        temprature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.profiles = profiles
        self.model = model
        self.temprature = temprature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "profiles": self.profiles,
                "model": self.model,
                "temprature": self.temprature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class SolidContentDto:
    content: str

    def __init__(self, content: str):
        self.content = content

    def __json__(self):
        return {
            "properties": {
                "content": self.content,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class ButtonDto:
    # type button
    button_name: str
    button_key: str

    def __init__(self, button_name: str, button_key: str):
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class LoginDto(ButtonDto):
    # type login
    button_name: str
    button_key: str

    def __init__(self, button_name: str, button_key: str):
        super().__init__(button_name, button_key)
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class GotoDtoItem:
    value: str
    type: str
    goto_id: str

    def __init__(self, value: str, type: str, goto_id: str):
        self.value = value
        self.type = type
        self.goto_id = goto_id

    def __json__(self):
        return {
            "value": self.value,
            "type": self.type,
            "goto_id": self.goto_id,
        }


@register_schema_to_swagger
class GotoSettings:
    items: list[GotoDtoItem]
    profile_key: str

    def __init__(self, items: list[GotoDtoItem], profile_key: str):
        self.items = items
        self.profile_key = profile_key

    def __json__(self):
        return {
            "items": self.items,
            "profile_key": self.profile_key,
        }


@register_schema_to_swagger
class GotoDto(ButtonDto):
    # type goto
    button_name: str
    button_key: str
    goto_settings: GotoSettings

    def __init__(self, button_name: str, button_key: str, goto_settings: GotoSettings):
        super().__init__(button_name, button_key)
        self.goto_settings = goto_settings

    def __json__(self):
        return {
            "properties": {
                "goto_settings": self.goto_settings,
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class PaymentDto(ButtonDto):
    # type payment
    button_name: str
    button_key: str

    def __init__(self, button_name: str, button_key: str):
        super().__init__(button_name, button_key)
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "properties": {
                "button_name": self.button_name,
                "button_key": self.button_key,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class ContinueDto(ButtonDto):
    # type continue
    button_name: str
    button_key: str

    def __init__(self, button_name: str, button_key: str):
        super().__init__(button_name, button_key)


@register_schema_to_swagger
class OptionDto:
    # type option
    option_name: str
    option_key: str
    profile_key: str
    buttons: list[ButtonDto]

    def __init__(
        self,
        option_name: str,
        option_key: str,
        profile_key: str,
        buttons: list[ButtonDto],
    ):
        self.option_name = option_name
        self.option_key = option_key
        self.profile_key = profile_key
        self.buttons = buttons

    def __json__(self):
        return {
            "properties": {
                "option_name": self.option_name,
                "option_key": self.option_key,
                "profile_key": self.profile_key,
                "buttons": self.buttons,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class InputDto:
    # type text input
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self, text_input_name: str, text_input_key: str, text_input_placeholder: str
    ):
        self.text_input_name = text_input_name
        self.text_input_key = text_input_key
        self.text_input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "properties": {
                "text_input_name": self.text_input_name,
                "text_input_key": self.text_input_key,
                "text_input_placeholder": self.text_input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class TextInputDto(InputDto):
    # type text input
    prompt: AIDto
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self,
        text_input_name: str = None,
        text_input_key: str = None,
        text_input_placeholder: str = None,
        prompt: AIDto = None,
    ):
        super().__init__(text_input_name, text_input_key, text_input_placeholder)
        self.prompt = prompt
        self.input_name = text_input_name
        self.input_key = text_input_key
        self.input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class CodeDto(InputDto):
    # type code
    input_name: str
    input_key: str
    input_placeholder: str

    def __init__(
        self, text_input_name: str, text_input_key: str, text_input_placeholder: str
    ):
        super().__init__(text_input_name, text_input_key, text_input_placeholder)
        self.input_name = text_input_name
        self.input_key = text_input_key
        self.input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "properties": {
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class PhoneDto(InputDto):
    # type phone
    input_name: str
    text_input_key: str
    text_input_placeholder: str

    def __init__(
        self, text_input_name: str, text_input_key: str, text_input_placeholder: str
    ):
        super().__init__(text_input_name, text_input_key, text_input_placeholder)
        self.input_name = text_input_name
        self.input_key = text_input_key
        self.input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "properties": {
                "input_name": self.input_name,
                "input_key": self.input_key,
                "input_placeholder": self.input_placeholder,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class BlockDto:
    block_id: str
    block_no: str
    block_name: str
    block_desc: str
    block_type: int
    block_index: int
    block_content: AIDto | SolidContentDto
    block_ui: OptionDto | TextInputDto | ButtonDto

    def __init__(
        self,
        block_id: str,
        block_no: str,
        block_name: str,
        block_desc: str,
        block_type: int,
        block_index: int,
        block_content: AIDto | SolidContentDto = None,
        block_ui: OptionDto | TextInputDto | ButtonDto = None,
    ):
        self.block_id = block_id
        self.block_no = block_no
        self.block_name = block_name
        self.block_desc = block_desc
        self.block_type = block_type
        self.block_index = block_index
        self.block_content = block_content
        self.block_ui = block_ui

    def __json__(self):
        return {
            "properties": {
                "block_id": self.block_id,
                "block_no": self.block_no,
                "block_name": self.block_name,
                "block_desc": self.block_desc,
                "block_type": self.block_type,
                "block_index": self.block_index,
                "block_content": self.block_content,
                "block_ui": self.block_ui,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


@register_schema_to_swagger
class OutlineEditDto:
    outline_id: str
    outline_no: str
    outline_name: str
    outline_desc: str
    outline_type: int
    outline_level: int

    def __init__(
        self,
        outline_id: str,
        outline_no: str,
        outline_name: str,
        outline_desc: str,
        outline_type: int,
        outline_level: int,
    ):
        self.outline_id = outline_id
        self.outline_no = outline_no
        self.outline_name = outline_name
        self.outline_desc = outline_desc
        self.outline_type = outline_type
        self.outline_level = outline_level

    def __json__(self):
        return {
            "properties": {
                "outline_id": self.outline_id,
                "outline_no": self.outline_no,
                "outline_name": self.outline_name,
                "outline_desc": self.outline_desc,
                "outline_type": self.outline_type,
                "outline_level": self.outline_level,
            },
            "type": "outline",
        }
