from flask import Flask

DICTS = {}


class DictItem:
    def __init__(self, display, value):
        self.display = display
        self.value = value

    def __json__(self):
        return {"display": self.display, "value": self.value}


class Dict:
    def __init__(self, name, display, items: list[DictItem]):
        self.name = name
        self.display = display
        self.items = items

    def __json__(self):
        return {"name": self.name, "display": self.display, "items": self.items}


def register_dict(name, desp, items: dict):
    if name in DICTS:
        return
    dictItems = []
    for key in items.keys():
        dictItems.append(DictItem(key, items[key]))
    DICTS[name] = Dict(name, desp, dictItems)


def get_all_dicts(app: Flask) -> dict:
    app.logger.info("get_all_dicts is called" + str(DICTS))
    return DICTS
