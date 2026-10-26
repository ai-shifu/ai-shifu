"""Resolve LLM settings for learning sessions."""

from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    """Normalize model settings used by learning runs."""

    model: str
    temperature: float
    usage_metadata: dict = Field(default_factory=dict)

    def __str__(self) -> str:
        """Return a concise model and temperature description."""
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self) -> str:
        """Return the same concise description as string conversion."""
        return self.__str__()

    def __json__(self) -> dict:
        """Return the LLM settings as JSON-compatible data."""
        return {"model": self.model, "temperature": self.temperature}
