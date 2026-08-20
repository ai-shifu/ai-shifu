from pydantic import BaseModel


class LLMSettings(BaseModel):
    model: str
    temperature: float

    def __str__(self) -> str:
        """Return a concise model and temperature description."""
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self) -> str:
        """Return the same concise description as string conversion."""
        return self.__str__()

    def __json__(self) -> dict:
        """Return the LLM settings as JSON-compatible data."""
        return {"model": self.model, "temperature": self.temperature}
