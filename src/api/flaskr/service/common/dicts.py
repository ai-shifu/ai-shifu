"""Register and serialize shared dictionary values."""

from flask import Flask

DICTS = {}


class DictItem:
    """Represent one key-label entry in a shared dictionary."""

    def __init__(self, display: object, value: object) -> None:
        """Create a display-value dictionary item."""
        self.display = display
        self.value = value

    def __json__(self) -> dict:
        """Return the dictionary item as JSON-compatible data."""
        return {"display": self.display, "value": self.value}


class Dict:
    """Index dictionary items by key for shared lookup helpers."""

    def __init__(self, name: object, display: object, items: list[DictItem]) -> None:
        """Create a named dictionary definition."""
        self.name = name
        self.display = display
        self.items = items

    def __json__(self) -> dict:
        """Return the dictionary definition as JSON-compatible data."""
        return {"name": self.name, "display": self.display, "items": self.items}


def register_dict(name: object, desp: object, items: dict):
    """Register dict."""
    if name in DICTS:
        return
    dict_items = []
    for key, value in items.items():
        dict_items.append(DictItem(key, value))
    DICTS[name] = Dict(name, desp, dict_items)


def get_all_dicts(app: Flask) -> dict:
    """Return all dicts."""
    app.logger.info("get_all_dicts is called %s", DICTS)
    return DICTS
