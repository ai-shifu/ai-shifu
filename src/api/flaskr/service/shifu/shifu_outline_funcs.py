from flaskr.framework.plugin.plugin_manager import extension
from .dtos import ReorderOutlineItemDto, SimpleOutlineDto
from .const import UNIT_TYPE_TRIAL
from .models import ShifuDraftOutlineItem
from ...dao import db
from ...util.uuid import generate_id
from ..common.models import raise_error
from datetime import datetime
from flaskr.service.check_risk.funcs import check_text_with_risk_control
from decimal import Decimal


# 新的大纲树节点类，用于处理ShifuDraftOutlineItem
class ShifuOutlineTreeNode:
    def __init__(self, outline_item: ShifuDraftOutlineItem):
        self.outline = outline_item
        self.children = []
        if outline_item:
            self.outline_id = outline_item.bid
            self.position = outline_item.position
        else:
            self.outline_id = ""
            self.position = ""
        self.parent_node = None

    def add_child(self, child: "ShifuOutlineTreeNode"):
        self.children.append(child)
        child.parent_node = self

    def remove_child(self, child: "ShifuOutlineTreeNode"):
        child.parent_node = None
        self.children.remove(child)

    def get_new_position(self):
        if not self.parent_node:
            return self.position
        else:
            return (
                self.parent_node.get_new_position()
                + f"{self.parent_node.children.index(self) + 1:02d}"
            )


# 获取现有大纲项目
def get_existing_outline_items(app, shifu_id: str) -> list[ShifuDraftOutlineItem]:
    with app.app_context():
        outline_items = ShifuDraftOutlineItem.query.filter_by(
            shifu_bid=shifu_id, latest=1, deleted=0
        ).all()
        return sorted(outline_items, key=lambda x: (len(x.position), x.position))


# 构建大纲树
def build_outline_tree(app, shifu_id: str) -> list[ShifuOutlineTreeNode]:
    outline_items = get_existing_outline_items(app, shifu_id)
    sorted_items = sorted(outline_items, key=lambda x: (len(x.position), x.position))
    outline_tree = []

    nodes_map = {}
    for item in sorted_items:
        node = ShifuOutlineTreeNode(item)
        nodes_map[item.position] = node

    # 构建树结构
    for position, node in nodes_map.items():
        if len(position) == 2:
            # 根节点
            outline_tree.append(node)
        else:
            # 找到父节点
            parent_position = position[:-2]
            if parent_position in nodes_map:
                parent_node = nodes_map[parent_position]
                if node not in parent_node.children:
                    parent_node.add_child(node)
            else:
                app.logger.error(f"Parent node not found for position: {position}")

    return outline_tree


@extension("get_outline_tree")
def get_outline_tree(result, app, user_id: str, shifu_id: str):
    """获取大纲树"""
    with app.app_context():
        outline_tree = build_outline_tree(app, shifu_id)
        outline_tree_dto = [
            SimpleOutlineDto(
                bid=node.outline_id,
                position=node.position,
                name=node.outline.title,
                children=[
                    SimpleOutlineDto(
                        bid=child.outline_id,
                        position=child.position,
                        name=child.outline.title,
                        children=[],
                    )
                    for child in node.children
                ],
            )
            for node in outline_tree
        ]
        return outline_tree_dto


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
    """创建大纲"""
    with app.app_context():
        # 生成新的大纲ID
        outline_id = generate_id(app)

        # 验证名称长度
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # 检查名称是否重复
        existing_outline = ShifuDraftOutlineItem.query.filter_by(
            shifu_bid=shifu_id, title=outline_name, latest=1, deleted=0
        ).first()
        if existing_outline:
            raise_error("SHIFU.OUTLINE_NAME_ALREADY_EXISTS")

        # 确定位置
        existing_items = get_existing_outline_items(app, shifu_id)
        if parent_id:
            # 子大纲
            parent_item = next(
                (item for item in existing_items if item.bid == parent_id), None
            )
            if not parent_item:
                raise_error("SHIFU.PARENT_OUTLINE_NOT_FOUND")

            # 找到同级别的最大索引
            siblings = [item for item in existing_items if item.parent_bid == parent_id]
            max_index = (
                max([int(item.position[-2:]) for item in siblings]) if siblings else 0
            )
            new_position = f"{parent_item.position}{max_index + 1:02d}"
        else:
            # 顶级大纲
            root_items = [item for item in existing_items if len(item.position) == 2]
            max_index = (
                max([int(item.position) for item in root_items]) if root_items else 0
            )
            new_position = f"{max_index + 1:02d}"

        # 创建新的大纲项目
        new_outline = ShifuDraftOutlineItem(
            bid=outline_id,
            shifu_bid=shifu_id,
            title=outline_name,
            parent_bid=parent_id or "",
            position=new_position,
            prerequisite_item_bids="",
            llm="",
            llm_temperature=Decimal("0.3"),
            llm_system_prompt=system_prompt or "",
            ask_enabled_status=5101,  # ASK_MODE_DEFAULT
            ask_llm="",
            ask_llm_temperature=Decimal("0.3"),
            ask_llm_system_prompt="",
            latest=1,
            version=1,
            deleted=0,
            created_user_bid=user_id,
            updated_user_bid=user_id,
        )

        # 风险检查
        check_text_with_risk_control(
            app, outline_id, user_id, f"{outline_name} {system_prompt or ''}"
        )

        # 保存到数据库
        db.session.add(new_outline)
        db.session.commit()

        return SimpleOutlineDto(
            bid=outline_id, position=new_position, name=outline_name, children=[]
        )


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
    """修改大纲"""
    with app.app_context():
        # 查找现有大纲
        existing_outline = ShifuDraftOutlineItem.query.filter_by(
            bid=outline_id, shifu_bid=shifu_id, latest=1, deleted=0
        ).first()

        if not existing_outline:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # 验证名称长度
        if len(outline_name) > 100:
            raise_error("SHIFU.OUTLINE_NAME_TOO_LONG")

        # 检查名称是否与其他大纲重复
        name_conflict = (
            ShifuDraftOutlineItem.query.filter_by(
                shifu_bid=shifu_id, title=outline_name, latest=1, deleted=0
            )
            .filter(ShifuDraftOutlineItem.bid != outline_id)
            .first()
        )

        if name_conflict:
            raise_error("SHIFU.OUTLINE_NAME_ALREADY_EXISTS")

        # 创建新版本
        existing_outline.latest = 0
        new_outline = existing_outline.clone()
        new_outline.title = outline_name
        new_outline.llm_system_prompt = system_prompt or ""
        new_outline.updated_user_bid = user_id
        new_outline.updated_at = datetime.now()

        # 风险检查
        check_text_with_risk_control(
            app, outline_id, user_id, f"{outline_name} {system_prompt or ''}"
        )

        # 保存到数据库
        db.session.add(new_outline)
        db.session.commit()

        return SimpleOutlineDto(
            bid=outline_id,
            position=new_outline.position,
            name=outline_name,
            children=[],
        )


@extension("delete_outline")
def delete_outline(result, app, user_id: str, shifu_id: str, outline_id: str):
    """删除大纲"""
    with app.app_context():
        # 查找要删除的大纲
        outline_to_delete = ShifuDraftOutlineItem.query.filter_by(
            bid=outline_id, shifu_bid=shifu_id, latest=1, deleted=0
        ).first()

        if not outline_to_delete:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # 构建大纲树以找到所有子节点
        outline_tree = build_outline_tree(app, shifu_id)

        # 找到要删除的节点
        def find_node_by_id(nodes, target_id):
            for node in nodes:
                if node.outline_id == target_id:
                    return node
                if node.children:
                    found = find_node_by_id(node.children, target_id)
                    if found:
                        return found
            return None

        node_to_delete = find_node_by_id(outline_tree, outline_id)
        if not node_to_delete:
            raise_error("SHIFU.OUTLINE_NOT_FOUND")

        # 收集所有要删除的节点ID（包括子节点）
        def collect_all_node_ids(node):
            ids = [node.outline_id]
            for child in node.children:
                ids.extend(collect_all_node_ids(child))
            return ids

        ids_to_delete = collect_all_node_ids(node_to_delete)

        # 标记所有相关大纲为删除状态
        for item_id in ids_to_delete:
            item = ShifuDraftOutlineItem.query.filter_by(
                bid=item_id, shifu_bid=shifu_id, latest=1, deleted=0
            ).first()
            if item:
                item.latest = 0
                new_item = item.clone()
                new_item.deleted = 1
                new_item.updated_user_bid = user_id
                new_item.updated_at = datetime.now()
                db.session.add(new_item)

        db.session.commit()
        return True


@extension("reorder_outline_tree")
def reorder_outline_tree(
    result, app, user_id: str, shifu_id: str, outlines: list[ReorderOutlineItemDto]
):
    """重新排序大纲树"""
    with app.app_context():
        app.logger.info(
            f"reorder outline tree, user_id: {user_id}, shifu_id: {shifu_id}"
        )

        # 获取现有大纲
        existing_items = get_existing_outline_items(app, shifu_id)
        existing_items_map = {item.bid: item for item in existing_items}

        # 重新构建位置
        def rebuild_positions(outline_dtos, parent_position=""):
            for i, outline_dto in enumerate(outline_dtos):
                if outline_dto.bid in existing_items_map:
                    item = existing_items_map[outline_dto.bid]
                    new_position = f"{parent_position}{i + 1:02d}"

                    if item.position != new_position:
                        # 创建新版本
                        item.latest = 0
                        new_item = item.clone()
                        new_item.position = new_position
                        new_item.updated_user_bid = user_id
                        new_item.updated_at = datetime.now()
                        db.session.add(new_item)
                        existing_items_map[outline_dto.bid] = new_item

                    # 递归处理子节点
                    if outline_dto.children:
                        rebuild_positions(outline_dto.children, new_position)

        rebuild_positions(outlines)
        db.session.commit()
        return True
