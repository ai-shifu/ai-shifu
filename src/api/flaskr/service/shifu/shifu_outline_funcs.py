from flaskr.framework.plugin.plugin_manager import extension
from .dtos import ReorderOutlineItemDto
from .const import UNIT_TYPE_TRIAL


@extension("get_outline_tree")
def get_outline_tree(result, app, user_id: str, shifu_id: str):
    app.logger.info(f"get_outline_tree: {result}")
    return result


@extension("create_outline")
def create_outline(
    result,
    app,
    user_id: str,
    shifu_id: str,
    parent_id: str,
    outline_name: str,
    outline_description: str,
    outline_index: int = 0,
    outline_type: str = UNIT_TYPE_TRIAL,
    system_prompt: str = None,
    is_hidden: bool = False,
):
    return result


@extension("modify_outline")
def modify_outline(
    result,
    app,
    user_id: str,
    shifu_id: str,
    outline_id: str,
    outline_name: str,
    outline_description: str,
    outline_index: int = 0,
    outline_type: str = UNIT_TYPE_TRIAL,
    system_prompt: str = None,
    is_hidden: bool = False,
):
    return result


@extension("delete_outline")
def delete_outline(result, app, user_id: str, shifu_id: str, outline_id: str):
    return result


@extension("reorder_outline_tree")
def reorder_outline_tree(
    result, app, user_id: str, shifu_id: str, outlines: list[ReorderOutlineItemDto]
):
    return result
