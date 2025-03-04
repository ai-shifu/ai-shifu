from flaskr.common.swagger import register_schema_to_swagger


@register_schema_to_swagger
class ScenarioDto:
    def __init__(
        self,
        scenario_id: str,
        scenario_name: str,
        scenario_description: str,
        scenario_image: str,
        scenario_state: int,
        is_favorite: bool,
    ):
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.scenario_description = scenario_description
        self.scenario_image = scenario_image
        self.scenario_state = scenario_state
        self.is_favorite = is_favorite

    def __json__(self):
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description,
            "scenario_image": self.scenario_image,
            "scenario_state": self.scenario_state,
            "is_favorite": self.is_favorite,
        }


@register_schema_to_swagger
class ChapterDto:
    def __init__(
        self,
        chapter_id: str,
        chapter_name: str,
        chapter_description: str,
        chapter_type: int,
    ):
        self.chapter_id = chapter_id
        self.chapter_name = chapter_name
        self.chapter_description = chapter_description
        self.chapter_type = chapter_type

    def __json__(self):
        return {
            "chapter_id": self.chapter_id,
            "chapter_name": self.chapter_name,
            "chapter_description": self.chapter_description,
            "chapter_type": self.chapter_type,
        }
