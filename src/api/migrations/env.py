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
    The simplest mode to avoid separation
    """
    # the system tables
    system_tables = [
        "alembic_version",
        "information_schema",
        "performance_schema",
        "mysql",
        "sys",
    ]

    if type_ == "table":
        # the system tables
        if name in system_tables or name.startswith("information_"):
            return False

        if reflected:
            # for the table reflected from the database, check if it has the corresponding model definition
            for mapper in db.Model.registry.mappers:
                model_class = mapper.class_
                if (
                    model_class.__module__.startswith("flaskr.service")
                    and mapper.local_table.name == name
                ):
                    return True
            # if not found the corresponding model, but not the system table, also include (for detection of deletion)
            return True
        else:
            # for the model table, check if it belongs to our service module
            if hasattr(object, "metadata"):
                for mapper in db.Model.registry.mappers:
                    if mapper.local_table is object:
                        model_class = mapper.class_
                        return model_class.__module__.startswith("flaskr.service")
            return False

    elif type_ in [
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
        "check_constraint",
    ]:
        # for the column, index, constraint, check if it belongs to our service module
        if hasattr(object, "table"):
            table_name = object.table.name
            # the system tables
            if table_name in system_tables or table_name.startswith("information_"):
                return False
            return True
        return False

    return True


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
                # filter out the duplicate or unnecessary operations
                filter_unnecessary_operations(script)

                # check if there are operations after filtering
                if script.upgrade_ops.is_empty():
                    directives[:] = []
                    logger.info("All detected changes were filtered as unnecessary.")
                else:
                    # check if it only contains meaningless type conversions
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

                    # if it only contains meaningless type conversions, skip the whole migration
                    if not has_meaningful_changes:
                        directives[:] = []
                        logger.info(
                            "Migration contains only meaningless type conversions - skipping migration generation."
                        )
                    else:
                        # merge the related changes into the same migration
                        merge_related_changes(script)

    def is_meaningful_operation(op):
        """judge if an operation is meaningful (not meaningless type conversion)"""
        op_type = type(op).__name__

        # for the ALTER COLUMN operation, check if it is meaningless type conversion
        if op_type == "AlterColumnOp":
            # if it is only type modification, check if it is meaningless conversion
            if hasattr(op, "modify_type") and op.modify_type is not None:
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # check if it is meaningless type conversion
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

                    # check if there are other meaningful modifications
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

                    # if it is only type conversion, without other modifications, it is not meaningful
                    if not has_other_changes:
                        return False

            # if there are other types of modifications, or it is not the filtered type conversion, it is meaningful
            return True

        # for other operation types (ADD COLUMN, DROP COLUMN, CREATE TABLE, etc.), it is meaningful
        if op_type in ["AddColumnOp", "DropColumnOp", "CreateTableOp", "DropTableOp"]:
            return True

        return True

    def filter_unnecessary_operations(script):
        """filter out the unnecessary or duplicate operations"""
        if not hasattr(script, "upgrade_ops") or not script.upgrade_ops:
            return

        original_ops = list(script.upgrade_ops.ops)
        filtered_ops = []
        seen_operations = set()

        for op in original_ops:
            # check if it is unnecessary operation
            if should_skip_operation(op):
                logger.info(
                    f"Skipping unnecessary operation: {type(op).__name__} on {getattr(op, 'table_name', 'unknown')}"
                )
                continue

            # generate the unique identifier of the operation to avoid duplication
            op_signature = get_operation_signature(op)
            if op_signature in seen_operations:
                logger.info(f"Skipping duplicate operation: {op_signature}")
                continue

            seen_operations.add(op_signature)
            filtered_ops.append(op)

        # update the operation list
        script.upgrade_ops.ops[:] = filtered_ops

        if len(filtered_ops) != len(original_ops):
            logger.info(
                f"Filtered operations from {len(original_ops)} to {len(filtered_ops)}"
            )

    def get_operation_signature(op):
        """generate the unique signature of the operation to detect duplication"""
        op_type = type(op).__name__

        if hasattr(op, "table_name"):
            table_name = op.table_name
            if hasattr(op, "column_name"):
                column_name = op.column_name
                # for the column operation, contains more detailed information
                if op_type == "AlterColumnOp":
                    # check the actual modified content
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
        """judge if it should skip the operation"""
        op_type = type(op).__name__

        # dynamically get the application table prefixes, based on the actual defined models
        def get_app_table_prefixes():
            """dynamically get the table prefixes from the actual models"""
            prefixes = set()

            # traverse all the registered models
            for mapper in db.Model.registry.mappers:
                model_class = mapper.class_
                # only check the models in the flaskr.service module
                if model_class.__module__.startswith("flaskr.service"):
                    table_name = mapper.local_table.name
                    # extract the table prefix (take the part before the first underscore and add an underscore)
                    if "_" in table_name:
                        prefix = table_name.split("_")[0] + "_"
                        prefixes.add(prefix)

            # add some special prefixes (compound prefixes)
            special_prefixes = ["draft_", "published_"]
            for prefix in special_prefixes:
                # check if there are tables with these prefixes at the beginning
                for mapper in db.Model.registry.mappers:
                    model_class = mapper.class_
                    if model_class.__module__.startswith("flaskr.service"):
                        table_name = mapper.local_table.name
                        if table_name.startswith(prefix):
                            prefixes.add(prefix)

            return list(prefixes)

        app_table_prefixes = get_app_table_prefixes()

        # the system tables
        system_tables = [
            "alembic_version",
            "information_schema",
            "performance_schema",
            "mysql",
            "sys",
        ]

        # skip the operations related to the system tables
        if hasattr(op, "table_name"):
            table_name = op.table_name
            if table_name in system_tables or table_name.startswith("information_"):
                return True

            # skip the tables that do not belong to the application
            if not any(table_name.startswith(prefix) for prefix in app_table_prefixes):
                return True

        # skip the empty or meaningless AlterColumnOp
        if op_type == "AlterColumnOp":
            # check if it is meaningless type conversion
            if hasattr(op, "modify_type") and op.modify_type is not None:
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # skip the DECIMAL ↔ NUMERIC conversion
                if (
                    "DECIMAL" in existing_type_str and "NUMERIC" in modify_type_str
                ) or ("NUMERIC" in existing_type_str and "DECIMAL" in modify_type_str):
                    return True

                # skip the TINYINT(1) ↔ BOOLEAN conversion
                if (
                    "TINYINT(1)" in existing_type_str and "BOOLEAN" in modify_type_str
                ) or (
                    "BOOLEAN" in existing_type_str and "TINYINT(1)" in modify_type_str
                ):
                    return True

            # check if it is a duplicate comment change (only modify the comment and is the "Update time" type of general comment)
            if hasattr(op, "modify_comment") and op.modify_comment is not None:
                existing_comment = str(
                    getattr(op, "existing_comment", "") or ""
                ).strip()
                modify_comment = str(op.modify_comment or "").strip()

                # if it is the "Update time" type of general comment, and there are no other modifications, skip
                if not existing_comment and modify_comment == "Update time":
                    # check if there are other modifications
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

            # check if there are substantial modifications
            has_meaningful_change = False

            if hasattr(op, "modify_comment") and op.modify_comment is not None:
                # for the comment change, do a more strict check
                existing_comment = str(
                    getattr(op, "existing_comment", "") or ""
                ).strip()
                modify_comment = str(op.modify_comment or "").strip()

                # if it is not the "Update time" type of general comment, it is meaningful
                if not (not existing_comment and modify_comment == "Update time"):
                    has_meaningful_change = True

            if (
                hasattr(op, "modify_server_default")
                and op.modify_server_default is not None
            ):
                has_meaningful_change = True
            if hasattr(op, "modify_type") and op.modify_type is not None:
                # but exclude the filtered type conversions
                existing_type_str = str(getattr(op, "existing_type", "")).upper()
                modify_type_str = str(op.modify_type).upper()

                # if it is the filtered type conversion, it is not meaningful
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

            # if there are no substantial modifications, skip
            if not has_meaningful_change:
                return True

            # check if it is a meaningless server_default change (for example, from None to None)
            if hasattr(op, "modify_server_default") and hasattr(
                op, "existing_server_default"
            ):
                new_default = op.modify_server_default
                existing_default = op.existing_server_default

                # if the new and old values are actually the same, skip
                if str(new_default) == str(existing_default):
                    return True

                # if both are None or empty values, skip
                if (new_default is None or new_default == "") and (
                    existing_default is None or existing_default == ""
                ):
                    return True

        return False

    def merge_related_changes(script):
        """merge the related changes into the same migration"""
        if not hasattr(script, "upgrade_ops") or not script.upgrade_ops:
            return

        # group the changes by table name
        table_changes = {}

        # collect all the changes
        for op in script.upgrade_ops.ops:
            if hasattr(op, "table_name"):
                table_name = op.table_name
                if table_name not in table_changes:
                    table_changes[table_name] = []
                table_changes[table_name].append(op)

        # check if there are changes that need to be merged
        for table_name, changes in table_changes.items():
            if len(changes) > 1:
                logger.info(
                    f"Table {table_name} has {len(changes)} changes, ensuring they are in the same migration"
                )

                # check if there are related change types
                change_types = [type(op).__name__ for op in changes]
                logger.info(f"Change types for {table_name}: {change_types}")

                # if the same table has comment and server_default changes, log
                has_comment_change = any("comment" in str(op).lower() for op in changes)
                has_server_default_change = any(
                    "server_default" in str(op).lower() for op in changes
                )

                if has_comment_change and has_server_default_change:
                    logger.info(
                        f"Table {table_name} has both comment and server_default changes - they should be in the same migration"
                    )

                # try to merge the related operations
                merged_ops = []
                i = 0
                while i < len(changes):
                    current_op = changes[i]
                    merged_ops.append(current_op)

                    # check if the next operation can be merged
                    if i + 1 < len(changes):
                        next_op = changes[i + 1]
                        # if both operations are alter_column and for the same column, try to merge
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
                            # here you can add the merge logic
                            i += 2  # skip the next operation
                            continue

                    i += 1

                # update the operation list
                if len(merged_ops) < len(changes):
                    logger.info(
                        f"Reduced operations for table {table_name} from {len(changes)} to {len(merged_ops)}"
                    )
                    # here you can update script.upgrade_ops.ops

    conf_args = current_app.extensions["migrate"].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    # set the migration configuration parameters - first set the basic parameters
    conf_args.setdefault("render_as_batch", True)

    # disable some options that may cause unnecessary migrations
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
