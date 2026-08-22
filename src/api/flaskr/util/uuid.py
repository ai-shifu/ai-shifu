"""Provide UUID utilities."""

import uuid

from flask import Flask


# generate a uuid
def generate_id(app: Flask) -> str:
    """Generate ID."""
    _ = app
    return str(uuid.uuid4()).replace("-", "")
