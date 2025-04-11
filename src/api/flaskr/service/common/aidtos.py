from ...common.swagger import register_schema_to_swagger


# prompt
@register_schema_to_swagger
class AIDto:
    prompt: str
    profiles: list[str]
    model: str
    temprature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        profiles: list[str] = None,
        model: str = None,
        temprature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.profiles = profiles
        self.model = model
        self.temprature = temprature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "profiles": self.profiles,
                "model": self.model,
                "temprature": self.temprature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }


# prompt
@register_schema_to_swagger
class SystemPromptDto:
    prompt: str
    profiles: list[str]
    model: str
    temprature: float
    other_conf: dict

    def __init__(
        self,
        prompt: str = None,
        profiles: list[str] = None,
        model: str = None,
        temprature: float = None,
        other_conf: dict = None,
    ):
        self.prompt = prompt
        self.profiles = profiles
        self.model = model
        self.temprature = temprature
        self.other_conf = other_conf

    def __json__(self):
        return {
            "properties": {
                "prompt": self.prompt,
                "profiles": self.profiles,
                "model": self.model,
                "temprature": self.temprature,
                "other_conf": self.other_conf,
            },
            "type": __class__.__name__.replace("Dto", "").lower(),
        }
