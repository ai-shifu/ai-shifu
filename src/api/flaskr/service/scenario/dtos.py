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
class PromptDto:
    prompt: str
    profiles: str
    model: str
    temprature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str,
        profiles: str,
        model: str,
        temprature: float,
        other_conf: dict,
    ):
        self.prompt = prompt
        self.profiles = profiles
        self.model = model
        self.temprature = temprature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "prompt": self.prompt,
            "profiles": self.profiles,
            "model": self.model,
            "temprature": self.temprature,
            "other_conf": self.other_conf,
        }


@register_schema_to_swagger
class ButtonDto:
    button_name: str
    button_key: str

    def __init__(self, button_name: str, button_key: str):
        self.button_name = button_name
        self.button_key = button_key

    def __json__(self):
        return {
            "button_name": self.button_name,
            "button_key": self.button_key,
        }


@register_schema_to_swagger
class ButtonGroupDto:
    button_group_name: str
    buttons: list[ButtonDto]

    def __init__(self, button_group_name: str, buttons: list[ButtonDto]):
        self.button_group_name = button_group_name
        self.buttons = buttons

    def __json__(self):
        return {
            "button_group_name": self.button_group_name,
            "buttons": [button.__json__() for button in self.buttons],
        }


@register_schema_to_swagger
class TextInputDto:
    text_input_name: str
    text_input_key: str
    text_input_placeholder: str

    def __init__(
        self, text_input_name: str, text_input_key: str, text_input_placeholder: str
    ):
        self.text_input_name = text_input_name
        self.text_input_key = text_input_key
        self.text_input_placeholder = text_input_placeholder

    def __json__(self):
        return {
            "text_input_name": self.text_input_name,
            "text_input_key": self.text_input_key,
            "text_input_placeholder": self.text_input_placeholder,
        }


@register_schema_to_swagger
class BlockDto:
    def __init__(
        self,
        block_id: str,
        block_no: str,
        block_name: str,
        block_desc: str,
        block_type: int,
        block_index: int,
        block_content: str,
        block_ui_type: int,
        block_ui_conf: dict,
    ):
        self.block_id = block_id
        self.block_no = block_no
        self.block_name = block_name
        self.block_desc = block_desc
        self.block_type = block_type
        self.block_index = block_index
        self.block_content = block_content
        self.block_ui_type = block_ui_type
        self.block_ui_conf = block_ui_conf

    def __json__(self):
        return {
            "block_id": self.block_id,
            "block_no": self.block_no,
            "block_name": self.block_name,
            "block_desc": self.block_desc,
            "block_type": self.block_type,
            "block_index": self.block_index,
            "block_content": self.block_content,
            "block_ui_type": self.block_ui_type,
            "block_ui_conf": self.block_ui_conf,
        }


@register_schema_to_swagger
class ScenarioTreeNodeDto:
    node_id: str
    node_no: str
    node_name: str
    node_desc: str
    children: list["ScenarioTreeNodeDto"]

    def __init__(
        self, node_id: str, node_no: str, node_name: str, node_desc: str, children: list
    ):
        self.node_id = node_id
        self.node_no = node_no
        self.node_name = node_name
        self.node_desc = node_desc
        self.children = children

    def __json__(self):
        return {
            "node_id": self.node_id,
            "node_no": self.node_no,
            "node_name": self.node_name,
            "node_desc": self.node_desc,
            "children": self.children,
        }
