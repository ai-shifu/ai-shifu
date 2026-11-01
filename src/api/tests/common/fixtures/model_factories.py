"""Build ORM rows for tests with the model's own scalar column defaults filled in.

Tests then pass only the fields they care about. Defaults come from the
model columns, so a factory row matches what the database would store for
an omitted field, and it already holds those values before the row is flushed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import inspect

if TYPE_CHECKING:
    from flaskr.service.billing.models import BillingOrder
    from flaskr.service.learn.models import (
        LearnGeneratedBlock,
        LearnGeneratedElement,
        LearnProgressRecord,
    )

ModelT = TypeVar("ModelT")


def build_row(model: type[ModelT], **overrides: object) -> ModelT:
    """Instantiate ``model`` with its scalar column defaults, then ``overrides``."""
    values: dict[str, object] = {}
    for attr in inspect(model).column_attrs:
        default = attr.columns[0].default
        if default is not None and default.is_scalar:
            values[attr.key] = default.arg
    values.update(overrides)
    return model(**values)


def make_generated_element(**overrides: object) -> LearnGeneratedElement:
    from flaskr.service.learn.models import LearnGeneratedElement

    return build_row(LearnGeneratedElement, **overrides)


def make_generated_block(**overrides: object) -> LearnGeneratedBlock:
    from flaskr.service.learn.models import LearnGeneratedBlock

    return build_row(LearnGeneratedBlock, **overrides)


def make_progress_record(**overrides: object) -> LearnProgressRecord:
    from flaskr.service.learn.models import LearnProgressRecord

    return build_row(LearnProgressRecord, **overrides)


def make_billing_order(**overrides: object) -> BillingOrder:
    from flaskr.service.billing.models import BillingOrder

    return build_row(BillingOrder, **overrides)
