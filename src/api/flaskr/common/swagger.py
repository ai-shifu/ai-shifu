"""Generate Swagger schemas from annotated DTOs."""

import ast
import inspect
import typing
from enum import Enum

from flasgger.base import BR_SANITIZER

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


def sanitize_swagger_docstring(text: str) -> str:
    """Preserve Flasgger formatting without inventing blank descriptions.

    D205 requires a blank line after a one-line summary. Flasgger passes that
    whitespace through its sanitizer and otherwise emits ``<br/>`` as an
    operation description.
    """
    stripped = text.strip()
    if not stripped:
        return ""
    return BR_SANITIZER(stripped)


def parse_comments(cls):
    """Extract field descriptions from a DTO's source comments."""
    source = inspect.getsource(cls)
    tree = ast.parse(source)
    comments = {}

    source_lines = source.splitlines()

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.AnnAssign, ast.Assign)):
                    if isinstance(item, ast.AnnAssign):
                        field_name = item.target.id
                    else:  # ast.Assign
                        field_name = item.targets[0].id

                    # ast line numbers are 1-based, list indexes are 0-based
                    line_num = item.lineno - 1
                    line = source_lines[line_num].strip()

                    if "#" in line:
                        comment = line.split("#", 1)[1].strip()
                        comments[field_name] = comment
                    elif item.value and isinstance(item.value, (ast.Str, ast.Constant)):
                        if isinstance(item.value, ast.Str):
                            comments[field_name] = item.value.s
                        elif isinstance(item.value, ast.Constant) and isinstance(
                            item.value.value, str
                        ):
                            comments[field_name] = item.value.value

    return comments


def get_field_schema(typ, description: str = ""):
    """Build the Swagger schema for an annotated DTO field."""
    field_schema = {}
    origin = typing.get_origin(typ)
    args = typing.get_args(typ)

    if isinstance(typ, type) and issubclass(typ, Enum):
        values = [member.value for member in typ]
        py_type = type(values[0]) if values else str
        json_type = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
        }.get(py_type, "string")
        field_schema["type"] = json_type
        field_schema["enum"] = values
        field_schema["description"] = f"Enum values: {', '.join(map(str, values))}"
    elif typ in (str, int, float, bool):
        field_schema["type"] = typ.__name__
        if typ is str:
            field_schema["type"] = "string"
        elif typ is int:
            field_schema["type"] = "integer"
        elif typ is float:
            field_schema["type"] = "number"
    elif origin in (typing.Union, getattr(__import__("types"), "UnionType", ())):
        union_types = typ.__args__ if hasattr(typ, "__args__") else args

        non_none_types = [t for t in union_types if t is not type(None)]

        if len(non_none_types) == 1:
            return get_field_schema(non_none_types[0], description)
        field_schema["oneOf"] = []
        for union_type in non_none_types:
            field_schema["oneOf"].append(get_field_schema(union_type))
    elif origin is list:
        item_type = args[0]
        field_schema["type"] = "array"
        field_schema["items"] = get_field_schema(item_type)
    elif origin is dict:
        _key_type, value_type = args
        field_schema["type"] = "object"
        field_schema["additionalProperties"] = get_field_schema(value_type)
    elif hasattr(typ, "__annotations__"):
        field_schema["$ref"] = f"#/components/schemas/{typ.__name__}"
    else:
        field_schema["type"] = "object"

    if description and not (isinstance(typ, type) and issubclass(typ, Enum)):
        field_schema["description"] = description
    return field_schema


def register_schema_to_swagger(cls):
    """Register schema to swagger."""
    if swagger_config["components"]["schemas"].get(cls.__name__, None):
        return swagger_config["components"]["schemas"].get(cls.__name__)

    if isinstance(cls, type) and issubclass(cls, Enum):
        schema = {
            "type": "string",
            "enum": [member.value for member in cls],
            "description": f"Enum values: {', '.join([member.value for member in cls])}",
        }
        swagger_config["components"]["schemas"][cls.__name__] = schema
        return cls

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
