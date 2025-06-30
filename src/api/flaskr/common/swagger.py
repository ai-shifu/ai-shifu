import typing
import ast
import inspect

swagger_config = {
    "openapi": "3.0.2",
    "info": {"title": "AI Shifu API", "version": "1.0.0"},
    "components": {"schemas": {}},
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
        }
    ],
    "swagger_ui_config": {
        "deepLinking": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 1,
        "defaultModelRendering": "example",
        "displayRequestDuration": True,
        "docExpansion": "none",
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True,
        "requestInterceptor": "function(request) { return request; }",
        "responseInterceptor": "function(response) { return response; }",
    },
}


def parse_comments(cls):
    source = inspect.getsource(cls)
    tree = ast.parse(source)
    comments = {}

    # 获取源代码的所有行
    source_lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.AnnAssign, ast.Assign)):
                    # 获取字段名
                    if isinstance(item, ast.AnnAssign):
                        field_name = item.target.id
                    else:  # ast.Assign
                        field_name = item.targets[0].id

                    # 获取行号
                    line_num = item.lineno - 1  # ast 行号从1开始，列表索引从0开始
                    line = source_lines[line_num].strip()

                    # 查找行内注释
                    if "#" in line:
                        comment = line.split("#", 1)[1].strip()
                        comments[field_name] = comment
                    # 如果没有注释但有字符串赋值，使用字符串值作为注释
                    elif item.value and isinstance(item.value, (ast.Str, ast.Constant)):
                        if isinstance(item.value, ast.Str):
                            comments[field_name] = item.value.s
                        elif isinstance(item.value, ast.Constant) and isinstance(
                            item.value.value, str
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
        field_schema = get_field_schema(typ, description=comments.get(name, ""))
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
