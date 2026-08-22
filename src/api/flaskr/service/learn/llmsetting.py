"""Resolve LLM settings for learning sessions."""

from pydantic import BaseModel


class LLMSettings(BaseModel):
    """Normalize model settings used by learning runs."""

    model: str
    temperature: float

    def __str__(self: object) -> str:
        """Return a concise model and temperature description."""
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self: object) -> str:
        """Return the same concise description as string conversion."""
        return self.__str__()

    def __json__(self: object) -> dict:
        """Return the LLM settings as JSON-compatible data."""
        return {"model": self.model, "temperature": self.temperature}
