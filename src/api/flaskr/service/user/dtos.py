import datetime

from flaskr.common.swagger import register_schema_to_swagger
from pydantic import BaseModel, Field


@register_schema_to_swagger
class UserProfileLabelItemDTO(BaseModel):
    key: str = Field(..., description="key", required=False)
    label: str = Field(..., description="label", required=False)
    type: str = Field(..., description="type", required=False)
    value: str | datetime.date | None = Field(..., description="value", required=False)
    items: list | None = Field(..., description="items", required=False)

    def __json__(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "value": self.value,
            "items": self.items,
        }


@register_schema_to_swagger
class UserProfileLabelDTO(BaseModel):
    profiles: list[UserProfileLabelItemDTO] = Field(
        ..., description="items", required=False
    )
    language: str = Field(..., description="language")

    def __json__(self) -> dict:
        return {
            "profiles": [item.__json__() for item in self.profiles],
            "language": self.language,
        }
