"""Bind the course host to the application-independent runtime and gateway."""

from flaskr.api import markdownflow as application
from flaskr.api.llm import markdownflow_model
from flaskr.service.learn import follow_up_memory_writer
from flaskr.service.learn.agent import lesson_entry, session_store
from markdownflow import Engine, Session, bridge


def test_course_uses_the_shared_native_types_and_runner() -> None:
    assert lesson_entry.Engine is application.Engine is Engine
    assert session_store.Session is application.Session is Session
    assert (
        follow_up_memory_writer.iter_turn is application.iter_turn is bridge.iter_turn
    )
    assert (
        lesson_entry.GatewayModel
        is application.GatewayModel
        is markdownflow_model.GatewayModel
    )
    assert markdownflow_model.turn_stop_requested is bridge.turn_stop_requested
