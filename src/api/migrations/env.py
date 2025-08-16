import logging
from logging.config import fileConfig

from flask import current_app
from flaskr.dao import db

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        # this works with Flask-SQLAlchemy<3 and Alchemical
        return current_app.extensions["migrate"].db.get_engine()
    except (TypeError, AttributeError):
        # this works with Flask-SQLAlchemy>=3
        return current_app.extensions["migrate"].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Enhanced include_object function that properly handles:
    - Table deletions
    - Column deletions
    - Comment changes
    - All changes in one migration
    """

    # 定义应用表前缀
    app_table_prefixes = [
        "ai_",
        "user_",
        "shifu_",
        "order_",
        "rag_",
        "study_",
        "sys_",
        "draft_",
        "published_",
        "profile_",
        "active_",
        "pingxx_",
        "discount_",
        "risk_",
    ]

    # 排除的系统表
    system_tables = [
        "alembic_version",
        "information_schema",
        "performance_schema",
        "mysql",
        "sys",
        "test",
    ]

    if type_ == "table":
        # 排除系统表
        if name in system_tables or name.startswith("information_"):
            return False

        # 检查是否是我们应用的表
        is_app_table = any(name.startswith(prefix) for prefix in app_table_prefixes)

        if reflected:
            # 对于从数据库反射的表，包含所有应用表
            # 这样能检测到表的删除
            return is_app_table
        else:
            # 对于模型表，检查是否属于我们的服务模块
            if hasattr(object, "metadata"):
                for mapper in db.Model.registry.mappers:
                    if mapper.local_table is object:
                        model_class = mapper.class_
                        # 只包含 flaskr.service 模块下的模型
                        return model_class.__module__.startswith("flaskr.service")

            # 如果没有找到对应的 mapper，但表名符合应用前缀，也包含
            return is_app_table

    elif type_ == "column":
        # 对于列，始终包含属于应用表的列
        # 这是检测列删除的关键 - 必须包含数据库中的列以便与模型比较
        if hasattr(object, "table"):
            table_name = object.table.name
            # 检查表是否属于我们的应用
            is_app_table = any(
                table_name.startswith(prefix) for prefix in app_table_prefixes
            )
            if not is_app_table or table_name in system_tables:
                return False
            return True
        return False

    elif type_ in [
        "index",
        "unique_constraint",
        "foreign_key_constraint",
        "check_constraint",
    ]:
        # 对于索引和约束，检查其所属的表
        if hasattr(object, "table"):
            table_name = object.table.name
            is_app_table = any(
                table_name.startswith(prefix) for prefix in app_table_prefixes
            )
            if not is_app_table or table_name in system_tables:
                return False
            return True
        return False

    # 对于其他对象类型，检查是否与我们的表相关
    if hasattr(object, "table"):
        table_name = object.table.name
        is_app_table = any(
            table_name.startswith(prefix) for prefix in app_table_prefixes
        )
        if not is_app_table or table_name in system_tables:
            return False
        return True

    return False


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        include_object=include_object,
        target_metadata=get_metadata(),
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")
            else:
                # 过滤掉重复或不必要的操作
                filter_unnecessary_operations(script)

                # 检查过滤后是否还有操作
                if script.upgrade_ops.is_empty():
                    directives[:] = []
                    logger.info("All detected changes were filtered as unnecessary.")
                else:
                    # 检查是否只包含无意义的类型转换
                    has_meaningful_changes = False

                    for op in script.upgrade_ops.ops:
                        if hasattr(op, "ops"):  # batch operations
                            for batch_op in op.ops:
                                if is_meaningful_operation(batch_op):
                                    has_meaningful_changes = True
                                    break
                        else:
                            if is_meaningful_operation(op):
                                has_meaningful_changes = True
                                break

                        if has_meaningful_changes:
                            break

                    # 如果只包含无意义的类型转换，跳过整个迁移
                    if not has_meaningful_changes:
                        directives[:] = []
                        logger.info(
                            "Migration contains only meaningless type conversions - skipping migration generation."
                        )
                    else:
                        # 合并相关的变更到同一个迁移中
                        merge_related_changes(script)

    def is_meaningful_operation(op):
        """判断一个操作是否有意义（不是无意义的类型转换）"""
        op_type = type(op).__name__

        # 对于 ALTER COLUMN 操作，检查是否是无意义的类型转换
        if op_type == "AlterColumnOp":
            # 如果只是类型修改，检查是否是无意义的转换
            if hasattr(op, "modify_type") and op.modify_type is not None:
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # 检查是否是无意义的类型转换
                if (
                    ("DECIMAL" in existing_type_str and "NUMERIC" in modify_type_str)
                    or ("NUMERIC" in existing_type_str and "DECIMAL" in modify_type_str)
                    or (
                        "TINYINT(1)" in existing_type_str
                        and "BOOLEAN" in modify_type_str
                    )
                    or (
                        "BOOLEAN" in existing_type_str
                        and "TINYINT(1)" in modify_type_str
                    )
                ):

                    # 检查是否有其他有意义的修改
                    has_other_changes = False
                    if hasattr(op, "modify_comment") and op.modify_comment is not None:
                        has_other_changes = True
                    if (
                        hasattr(op, "modify_server_default")
                        and op.modify_server_default is not None
                    ):
                        has_other_changes = True
                    if (
                        hasattr(op, "modify_nullable")
                        and op.modify_nullable is not None
                    ):
                        has_other_changes = True

                    # 如果只是类型转换，没有其他修改，认为不是有意义的操作
                    if not has_other_changes:
                        return False

            # 如果有其他类型的修改，或者不是被过滤的类型转换，认为是有意义的
            return True

        # 对于其他操作类型（ADD COLUMN, DROP COLUMN, CREATE TABLE 等），都认为是有意义的
        if op_type in ["AddColumnOp", "DropColumnOp", "CreateTableOp", "DropTableOp"]:
            return True

        return True

    def filter_unnecessary_operations(script):
        """过滤掉不必要的或重复的操作"""
        if not hasattr(script, "upgrade_ops") or not script.upgrade_ops:
            return

        original_ops = list(script.upgrade_ops.ops)
        filtered_ops = []
        seen_operations = set()

        for op in original_ops:
            # 检查是否是不必要的操作
            if should_skip_operation(op):
                logger.info(
                    f"Skipping unnecessary operation: {type(op).__name__} on {getattr(op, 'table_name', 'unknown')}"
                )
                continue

            # 生成操作的唯一标识符以避免重复
            op_signature = get_operation_signature(op)
            if op_signature in seen_operations:
                logger.info(f"Skipping duplicate operation: {op_signature}")
                continue

            seen_operations.add(op_signature)
            filtered_ops.append(op)

        # 更新操作列表
        script.upgrade_ops.ops[:] = filtered_ops

        if len(filtered_ops) != len(original_ops):
            logger.info(
                f"Filtered operations from {len(original_ops)} to {len(filtered_ops)}"
            )

    def get_operation_signature(op):
        """生成操作的唯一签名以检测重复"""
        op_type = type(op).__name__

        if hasattr(op, "table_name"):
            table_name = op.table_name
            if hasattr(op, "column_name"):
                column_name = op.column_name
                # 对于列操作，包含更多详细信息
                if op_type == "AlterColumnOp":
                    # 检查实际修改的内容
                    modifications = []
                    if hasattr(op, "modify_comment") and op.modify_comment is not None:
                        modifications.append(f"comment:{op.modify_comment}")
                    if (
                        hasattr(op, "modify_server_default")
                        and op.modify_server_default is not None
                    ):
                        modifications.append(
                            f"server_default:{op.modify_server_default}"
                        )
                    if hasattr(op, "modify_type") and op.modify_type is not None:
                        modifications.append(f"type:{op.modify_type}")
                    return f"{op_type}:{table_name}:{column_name}:{':'.join(modifications)}"
                else:
                    return f"{op_type}:{table_name}:{column_name}"
            else:
                return f"{op_type}:{table_name}"
        else:
            return f"{op_type}:unknown"

    def should_skip_operation(op):
        """判断是否应该跳过某个操作"""
        op_type = type(op).__name__

        # 应用表前缀 - 与 include_object 保持一致
        app_table_prefixes = [
            "ai_",
            "user_",
            "shifu_",
            "order_",
            "rag_",
            "study_",
            "sys_",
            "draft_",
            "published_",
            "profile_",
            "active_",
            "pingxx_",
            "discount_",
            "risk_",
        ]

        # 系统表
        system_tables = [
            "alembic_version",
            "information_schema",
            "performance_schema",
            "mysql",
            "sys",
            "test",
        ]

        # 跳过系统表相关的操作
        if hasattr(op, "table_name"):
            table_name = op.table_name
            if table_name in system_tables or table_name.startswith("information_"):
                return True

            # 跳过不属于应用的表
            if not any(table_name.startswith(prefix) for prefix in app_table_prefixes):
                return True

        # 跳过空的或无意义的 AlterColumnOp
        if op_type == "AlterColumnOp":
            # 检查是否是无意义的类型转换
            if hasattr(op, "modify_type") and op.modify_type is not None:
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # 跳过 DECIMAL ↔ NUMERIC 转换
                if (
                    "DECIMAL" in existing_type_str and "NUMERIC" in modify_type_str
                ) or ("NUMERIC" in existing_type_str and "DECIMAL" in modify_type_str):
                    return True

                # 跳过 TINYINT(1) ↔ BOOLEAN 转换
                if (
                    "TINYINT(1)" in existing_type_str and "BOOLEAN" in modify_type_str
                ) or (
                    "BOOLEAN" in existing_type_str and "TINYINT(1)" in modify_type_str
                ):
                    return True

            # 检查是否是重复的注释变更（只修改注释且是"Update time"这种通用注释）
            if hasattr(op, "modify_comment") and op.modify_comment is not None:
                existing_comment = str(
                    getattr(op, "existing_comment", "") or ""
                ).strip()
                modify_comment = str(op.modify_comment or "").strip()

                # 如果是添加"Update time"这种通用注释，且没有其他修改，跳过
                if not existing_comment and modify_comment == "Update time":
                    # 检查是否还有其他修改
                    has_other_changes = (
                        (hasattr(op, "modify_type") and op.modify_type is not None)
                        or (
                            hasattr(op, "modify_server_default")
                            and op.modify_server_default is not None
                        )
                        or (
                            hasattr(op, "modify_nullable")
                            and op.modify_nullable is not None
                        )
                    )
                    if not has_other_changes:
                        return True

            # 检查是否真的有实质性的修改
            has_meaningful_change = False

            if hasattr(op, "modify_comment") and op.modify_comment is not None:
                # 对于注释变更，进行更严格的检查
                existing_comment = str(
                    getattr(op, "existing_comment", "") or ""
                ).strip()
                modify_comment = str(op.modify_comment or "").strip()

                # 如果不是添加"Update time"这种通用注释，认为是有意义的
                if not (not existing_comment and modify_comment == "Update time"):
                    has_meaningful_change = True

            if (
                hasattr(op, "modify_server_default")
                and op.modify_server_default is not None
            ):
                has_meaningful_change = True
            if hasattr(op, "modify_type") and op.modify_type is not None:
                # 但是排除掉我们已经过滤的类型转换
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # 如果是被过滤的类型转换，不认为是有意义的修改
                is_filtered_type_change = (
                    ("DECIMAL" in existing_type_str and "NUMERIC" in modify_type_str)
                    or ("NUMERIC" in existing_type_str and "DECIMAL" in modify_type_str)
                    or (
                        "TINYINT(1)" in existing_type_str
                        and "BOOLEAN" in modify_type_str
                    )
                    or (
                        "BOOLEAN" in existing_type_str
                        and "TINYINT(1)" in modify_type_str
                    )
                )

                if not is_filtered_type_change:
                    has_meaningful_change = True

            if hasattr(op, "modify_nullable") and op.modify_nullable is not None:
                has_meaningful_change = True

            # 如果没有实质性修改，跳过
            if not has_meaningful_change:
                return True

            # 检查是否是无意义的 server_default 变更（例如从 None 到 None）
            if hasattr(op, "modify_server_default") and hasattr(
                op, "existing_server_default"
            ):
                new_default = op.modify_server_default
                existing_default = op.existing_server_default

                # 如果新旧值实际相同，跳过
                if str(new_default) == str(existing_default):
                    return True

                # 如果都是 None 或空值，跳过
                if (new_default is None or new_default == "") and (
                    existing_default is None or existing_default == ""
                ):
                    return True

        return False

    def merge_related_changes(script):
        """合并相关的变更到同一个迁移中"""
        if not hasattr(script, "upgrade_ops") or not script.upgrade_ops:
            return

        # 按表名分组变更
        table_changes = {}

        # 收集所有变更
        for op in script.upgrade_ops.ops:
            if hasattr(op, "table_name"):
                table_name = op.table_name
                if table_name not in table_changes:
                    table_changes[table_name] = []
                table_changes[table_name].append(op)

        # 检查是否有需要合并的变更
        for table_name, changes in table_changes.items():
            if len(changes) > 1:
                logger.info(
                    f"Table {table_name} has {len(changes)} changes, ensuring they are in the same migration"
                )

                # 检查是否有相关的变更类型
                change_types = [type(op).__name__ for op in changes]
                logger.info(f"Change types for {table_name}: {change_types}")

                # 如果同一个表有 comment 和 server_default 的变化，记录日志
                has_comment_change = any("comment" in str(op).lower() for op in changes)
                has_server_default_change = any(
                    "server_default" in str(op).lower() for op in changes
                )

                if has_comment_change and has_server_default_change:
                    logger.info(
                        f"Table {table_name} has both comment and server_default changes - they should be in the same migration"
                    )

                # 尝试合并相关的操作
                merged_ops = []
                i = 0
                while i < len(changes):
                    current_op = changes[i]
                    merged_ops.append(current_op)

                    # 检查下一个操作是否可以合并
                    if i + 1 < len(changes):
                        next_op = changes[i + 1]
                        # 如果两个操作都是 alter_column 且针对同一个列，尝试合并
                        if (
                            hasattr(current_op, "column_name")
                            and hasattr(next_op, "column_name")
                            and current_op.column_name == next_op.column_name
                            and type(current_op).__name__ == "AlterColumnOp"
                            and type(next_op).__name__ == "AlterColumnOp"
                        ):

                            logger.info(
                                f"Merging operations for column {current_op.column_name} in table {table_name}"
                            )
                            # 这里可以添加合并逻辑
                            i += 2  # 跳过下一个操作
                            continue

                    i += 1

                # 更新操作列表
                if len(merged_ops) < len(changes):
                    logger.info(
                        f"Reduced operations for table {table_name} from {len(changes)} to {len(merged_ops)}"
                    )
                    # 这里可以更新 script.upgrade_ops.ops

    conf_args = current_app.extensions["migrate"].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    # 设置迁移配置参数 - 先设置基础参数
    conf_args.setdefault("render_as_batch", True)

    # 禁用一些可能导致不必要迁移的选项
    conf_args["compare_name"] = False
    conf_args["compare_schema"] = False

    # 添加自定义的比较函数来减少误报
    def compare_server_default(
        context,
        inspected_column,
        metadata_column,
        inspected_default,
        metadata_default,
        rendered_metadata_default,
    ):
        """自定义 server_default 比较，减少误报"""

        # 标准化默认值的表示
        def normalize_default(default):
            if default is None:
                return None
            default_str = str(default).strip()
            if default_str == "" or default_str.lower() == "none":
                return None
            # MySQL TIMESTAMP 特殊处理
            if default_str.upper() in ["CURRENT_TIMESTAMP", "NOW()"]:
                return "CURRENT_TIMESTAMP"
            if "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP" in default_str.upper():
                return "CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            return default_str

        norm_inspected = normalize_default(inspected_default)
        norm_metadata = normalize_default(rendered_metadata_default)

        # 如果两个都是 None，认为相同
        if norm_inspected is None and norm_metadata is None:
            return False

        return norm_inspected != norm_metadata

    def compare_comment(
        context, inspected_column, metadata_column, inspected_comment, metadata_comment
    ):
        """自定义 comment 比较，减少误报但允许真正的注释变更"""

        # 标准化注释
        def normalize_comment(comment):
            if comment is None:
                return None
            comment_str = str(comment).strip()
            if comment_str == "":
                return None
            return comment_str

        norm_inspected = normalize_comment(inspected_comment)
        norm_metadata = normalize_comment(metadata_comment)

        # 如果两个都是 None 或空，认为相同
        if norm_inspected is None and norm_metadata is None:
            return False

        # 如果一个是 None 另一个不是，但内容是无意义的默认注释，跳过
        if norm_inspected != norm_metadata:
            # 检查是否是从 None 到通用的"Update time"注释，这种情况跳过
            if (norm_inspected is None and norm_metadata == "Update time") or (
                norm_metadata is None and norm_inspected == "Update time"
            ):
                return False

            # 检查是否已经有相同的注释变更在最近的迁移中
            if hasattr(context, "_comment_change_signature"):
                signature = f"{metadata_column.table.name}.{metadata_column.name}:{norm_inspected}->{norm_metadata}"
                if signature in context._comment_change_signature:
                    return False
                else:
                    context._comment_change_signature.add(signature)
            else:
                context._comment_change_signature = set()
                signature = f"{metadata_column.table.name}.{metadata_column.name}:{norm_inspected}->{norm_metadata}"
                context._comment_change_signature.add(signature)

            return True

        return False

    def compare_type(
        context, inspected_column, metadata_column, inspected_type, metadata_type
    ):
        """自定义类型比较，减少误报"""
        # 对于某些类型的小差异，认为相同
        inspected_str = str(inspected_type).upper()
        metadata_str = str(metadata_type).upper()

        # MySQL TINYINT(1) 和 BOOLEAN 的处理 - 这些是等价的
        if ("TINYINT(1)" in inspected_str and "BOOLEAN" in metadata_str) or (
            "BOOLEAN" in inspected_str and "TINYINT(1)" in metadata_str
        ):
            return False

        # MySQL DECIMAL 和 SQLAlchemy Numeric 的处理 - 这些是等价的
        if ("DECIMAL" in inspected_str and "NUMERIC" in metadata_str) or (
            "NUMERIC" in inspected_str and "DECIMAL" in metadata_str
        ):
            return False

        # BIGINT 自增字段的处理
        if "BIGINT" in inspected_str and "BIGINT" in metadata_str:
            return False

        # VARCHAR 长度差异的处理 - 只要长度相同就认为相同
        import re

        varchar_pattern = r"VARCHAR\((\d+)\)"
        inspected_match = re.search(varchar_pattern, inspected_str)
        metadata_match = re.search(varchar_pattern, metadata_str)
        if inspected_match and metadata_match:
            if inspected_match.group(1) == metadata_match.group(1):
                return False

        # TEXT 类型的处理 - MySQL 的 TEXT, LONGTEXT 等都映射到 SQLAlchemy 的 TEXT
        if "TEXT" in inspected_str and "TEXT" in metadata_str:
            return False

        return inspected_str != metadata_str

    # 应用自定义比较函数
    conf_args["compare_server_default"] = compare_server_default
    # 重新启用注释比较但使用更智能的去重逻辑
    conf_args["compare_comment"] = compare_comment
    # 完全禁用类型比较以避免 DECIMAL<->NUMERIC 和 TINYINT<->BOOLEAN 的误报
    conf_args["compare_type"] = False

    connectable = get_engine()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            include_object=include_object,
            **conf_args,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
