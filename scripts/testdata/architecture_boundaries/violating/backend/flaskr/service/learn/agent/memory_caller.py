"""Fixture: in-service import of the moved learn memory package."""

from flaskr.service.learn.memory import load_memory


def caller() -> object:
    return load_memory
