"""A library may depend on portable SDK contracts."""

from pydantic_ai.models import Model


def model_type() -> type:
    return Model
