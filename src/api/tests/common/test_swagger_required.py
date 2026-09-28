"""Keep OpenAPI required fields aligned with DTO validation."""

from flaskr.common.swagger import register_schema_to_swagger, swagger_config
from pydantic import BaseModel, Field


@register_schema_to_swagger
class SwaggerRequiredFieldsFixture(BaseModel):
    """Exercise requiredness independently from nullable values."""

    required_value: str
    required_nullable: str | None = Field(...)
    optional_nullable: str | None = None
    defaulted_value: str = "default"
    factory_value: list[str] = Field(default_factory=list)


@register_schema_to_swagger
class SwaggerOptionalFieldsFixture(BaseModel):
    """Exercise a request with no required fields."""

    optional_value: str | None = None
    factory_value: list[str] = Field(default_factory=list)


@register_schema_to_swagger
class SwaggerPlainFieldsFixture:
    """Preserve the existing non-Pydantic DTO contract."""

    value: str
    nullable_value: str | None


def test_pydantic_openapi_requiredness_matches_validation() -> None:
    schema = swagger_config["components"]["schemas"]["SwaggerRequiredFieldsFixture"]
    assert schema["required"] == ["required_value", "required_nullable"]
    assert set(schema["properties"]) == {
        "required_value",
        "required_nullable",
        "optional_nullable",
        "defaulted_value",
        "factory_value",
    }
    dto = SwaggerRequiredFieldsFixture(required_value="value", required_nullable=None)
    assert dto.factory_value == []


def test_plain_dto_required_fields_are_unchanged() -> None:
    schema = swagger_config["components"]["schemas"]["SwaggerPlainFieldsFixture"]
    assert schema["required"] == ["value", "nullable_value"]


def test_optional_dto_omits_empty_required_array() -> None:
    schema = swagger_config["components"]["schemas"]["SwaggerOptionalFieldsFixture"]
    assert "required" not in schema
    assert set(schema["properties"]) == {"optional_value", "factory_value"}
