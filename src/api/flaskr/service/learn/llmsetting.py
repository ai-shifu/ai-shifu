from pydantic import BaseModel


class LLMSettings(BaseModel):
    model: str
    temperature: float

    def __str__(self) -> str:
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self) -> str:
        return self.__str__()

    def __json__(self) -> dict:
        return {"model": self.model, "temperature": self.temperature}
