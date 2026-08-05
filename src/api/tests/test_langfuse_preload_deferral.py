"""Langfuse init must not create a real client in the gunicorn preload master.

A real client starts the Langfuse/OTel BatchProcessor worker thread in the
master and registers an at-fork restart hook; after fork every worker
revives the orphaned processor's thread, whose gevent threading bookkeeping
crashes the hub (KeyError in AbstractLinkable._notify_links) and can
interrupt unrelated in-flight DB exchanges.
"""

import flaskr.api.langfuse as langfuse_module
from flaskr.api.langfuse import MockClient, init_langfuse


class _RecordingLangfuse:
    instances = []

    def __init__(self, **kwargs):
        _RecordingLangfuse.instances.append(kwargs)


def _configure(app):
    app.config["LANGFUSE_PUBLIC_KEY"] = "pk"
    app.config["LANGFUSE_SECRET_KEY"] = "sk"
    app.config["LANGFUSE_HOST"] = "https://langfuse.example"


def test_preload_master_defers_real_client(app, monkeypatch):
    _configure(app)
    monkeypatch.setattr(langfuse_module, "Langfuse", _RecordingLangfuse)
    monkeypatch.setattr(_RecordingLangfuse, "instances", [])
    monkeypatch.setenv(langfuse_module.PRELOAD_MASTER_ENV, "1")

    init_langfuse(app)

    assert _RecordingLangfuse.instances == []
    assert isinstance(langfuse_module.langfuse_client, MockClient)


def test_worker_builds_real_client_after_flag_cleared(app, monkeypatch):
    _configure(app)
    monkeypatch.setattr(langfuse_module, "Langfuse", _RecordingLangfuse)
    monkeypatch.setattr(_RecordingLangfuse, "instances", [])
    monkeypatch.delenv(langfuse_module.PRELOAD_MASTER_ENV, raising=False)

    init_langfuse(app)

    assert len(_RecordingLangfuse.instances) == 1
    assert _RecordingLangfuse.instances[0]["host"] == "https://langfuse.example"
