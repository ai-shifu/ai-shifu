"""Memory contracts independent of the backing profile persistence DTOs."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class VariableMemoryUpdate:
    """One variable assignment; staging maps its value for update events.

    Variable keys and definition IDs belong to this category, not to every
    future kind of memory. The backing writer owns storage normalization.
    """

    key: str
    value: str
    definition_bid: str = ""


@dataclass(slots=True)
class MemoryUpdate:
    """An explicit memory patch; omitted items are not replaced or deleted.

    Variables are the first supported category. Future categories need their
    own typed fields and persistence handlers, rather than synthetic variables.
    """

    variables: list[VariableMemoryUpdate] = field(default_factory=list)


@dataclass(slots=True)
class MemorySnapshot:
    """A runtime memory view, with each supported category kept separate."""

    variables: dict[str, str] = field(default_factory=dict)

    def as_variables(self) -> dict[str, str]:
        """Project only variables for prompts without mutating the memory view."""
        return dict(self.variables)
