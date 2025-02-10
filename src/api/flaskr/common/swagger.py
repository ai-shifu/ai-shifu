import typing
import ast
import inspect

swagger_config = {
    "openapi": "3.0.2",
    "info": {"title": "AI 师傅 - API 文档", "version": "1.0.0"},
    # "optional_fields": ["components"],
    "components": {"schemas": {}},
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
        }
    ],
    "common_parameters": [
        {
            "name": "X-Request-ID",
            "in": "header",
            "required": False,
            "schema": {"type": "string", "description": "请求唯一标识符"},
        },
    ],
}


def parse_comments(cls):
    source = inspect.getsource(cls)
    tree = ast.parse(source)
    comments = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) or isinstance(item, ast.Assign):
                    # Handle both annotated assignments and regular assignments
                    if isinstance(item, ast.AnnAssign):
                        field_name = item.target.id
                    else:  # it must be ast.Assign
                        field_name = item.targets[0].id
                    if item.value and isinstance(item.value, ast.Str):
                        comments[field_name] = item.value.s
                    elif (
                        item.value
                        and isinstance(item.value, ast.Constant)
                        and isinstance(item.value.value, str)
                    ):
                        comments[field_name] = item.value.value
    return comments


def get_field_schema(typ, description: str = ""):
    field_schema = {}
    origin = typing.get_origin(typ)
    args = typing.get_args(typ)

    if typ in (str, int, float, bool):
        field_schema["type"] = typ.__name__
        if typ == str:
            field_schema["type"] = "string"
        elif typ == int:
            field_schema["type"] = "integer"
        elif typ == float:
            field_schema["type"] = "number"
    # 处理列表类型
    elif origin == list:
        item_type = args[0]
        field_schema["type"] = "array"
        field_schema["items"] = get_field_schema(item_type)
    elif origin == dict:
        key_type, value_type = args
        field_schema["type"] = "object"
        field_schema["additionalProperties"] = get_field_schema(value_type)
    elif hasattr(typ, "__annotations__"):
        field_schema["$ref"] = f"#/components/schemas/{typ.__name__}"
    else:
        field_schema["type"] = "object"
    if description:
        field_schema["description"] = description
    return field_schema


def register_schema_to_swagger(cls):
    if swagger_config["components"]["schemas"].get(cls.__name__, None):
        return swagger_config["components"]["schemas"].get(cls.__name__)
    properties = {}
    required = []
    comments = parse_comments(cls)

    for name, typ in cls.__annotations__.items():
        field_schema = get_field_schema(typ)
        properties[name] = field_schema
        required.append(name)
    schema = {
        "type": "object",
        "description": comments.get(cls.__name__, ""),
        "properties": properties,
        "required": required,
    }
    swagger_config["components"]["schemas"][cls.__name__] = schema

    return cls
