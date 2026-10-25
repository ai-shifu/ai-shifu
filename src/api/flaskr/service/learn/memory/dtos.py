"""Memory contracts independent of the backing profile persistence DTOs."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class VariableMemoryUpdate:
    """One memory entry projected onto the legacy profile persistence contract.

    Historical adapter names and optional definition IDs remain compatible with
    stored profile rows. A question answer needs no definition record.
    """

    key: str
    value: str
    definition_bid: str = ""


@dataclass(slots=True)
class MemoryUpdate:
    """An explicit memory patch; omitted items are not replaced or deleted.

    The historical ``variables`` member is a compatibility field for keyed
    memory entries, including question answers without profile definitions.
    """

    variables: list[VariableMemoryUpdate] = field(default_factory=list)


@dataclass(slots=True)
class MemorySnapshot:
    """Keyed learner memory exposed through the legacy profile adapter fields."""

    variables: dict[str, str] = field(default_factory=dict)

    def as_variables(self) -> dict[str, str]:
        """Copy memory entries through the historical profile-adapter method name."""
        return dict(self.variables)
