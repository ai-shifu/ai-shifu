import uuid

from flask import Flask


# generate a uuid
def generate_id(app: Flask) -> str:
    return str(uuid.uuid4()).replace("-", "")
