from pydantic import BaseModel


class LLMSettings(BaseModel):
    model: str
    temperature: float

    def __str__(self):
        return f"model: {self.model}, temperature: {self.temperature}"

    def __repr__(self):
        return self.__str__()

    def __json__(self):
        return {"model": self.model, "temperature": self.temperature}
