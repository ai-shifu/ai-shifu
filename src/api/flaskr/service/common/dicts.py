from flask import Flask

DICTS = {}


class DictItem:
    def __init__(self, display, value) -> None:
        self.display = display
        self.value = value

    def __json__(self) -> dict:
        return {"display": self.display, "value": self.value}


class Dict:
    def __init__(self, name, display, items: list[DictItem]) -> None:
        self.name = name
        self.display = display
        self.items = items

    def __json__(self) -> dict:
        return {"name": self.name, "display": self.display, "items": self.items}


def register_dict(name, desp, items: dict):
    if name in DICTS:
        return
    dict_items = []
    for key, value in items.items():
        dict_items.append(DictItem(key, value))
    DICTS[name] = Dict(name, desp, dict_items)


def get_all_dicts(app: Flask) -> dict:
    app.logger.info("get_all_dicts is called %s", DICTS)
    return DICTS
