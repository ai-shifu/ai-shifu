from langfuse import Langfuse
from flask import Flask


class MockClient:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        def method(*args, **kwargs):
            return self

        return method


def init_langfuse(app: Flask):
    global langfuse_client
    app.logger.info("Initializing Langfuse client")
    if (
        app.config.get("LANGFUSE_PUBLIC_KEY")
        and app.config.get("LANGFUSE_SECRET_KEY")
        and app.config.get("LANGFUSE_HOST")
    ):
        langfuse_client = Langfuse(
            public_key=app.config["LANGFUSE_PUBLIC_KEY"],
            secret_key=app.config["LANGFUSE_SECRET_KEY"],
            host=app.config["LANGFUSE_HOST"],
        )
    else:
        app.logger.warning("Langfuse configuration not found, using MockLangfuse")
        langfuse_client = MockClient()
