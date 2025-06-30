from ...common.swagger import register_schema_to_swagger


# prompt
@register_schema_to_swagger
class AIDto:
    prompt: str
    variables: list[str]
    model: str
    temperature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        variables: list[str] = None,
        model: str = None,
        temperature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.variables = variables
        self.model = model
        self.temperature = temperature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "variables": self.variables,
                "model": self.model,
                "temperature": self.temperature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


# prompt
@register_schema_to_swagger
class SystemPromptDto:
    prompt: str
    variables: list[str]
    model: str
    temperature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        variables: list[str] = None,
        model: str = None,
        temperature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.variables = variables
        self.model = model
        self.temperature = temperature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "variables": self.variables,
                "model": self.model,
                "temperature": self.temperature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }
