"""Keep application hosts bound to a single native runtime and gateway adapter."""

from flaskr.api import markdownflow as application
from flaskr.api.llm import markdownflow_model
from flaskr.service.learn.agent import lesson_entry, session_store
from flaskr.service.learn.ask import memory_writer as follow_up_memory_writer
from flaskr.service.profile_research import engine_runtime, provider
from markdownflow import Engine, Session, bridge


def test_course_and_profile_share_native_types_and_runner() -> None:
    assert lesson_entry.Engine is engine_runtime.Engine is application.Engine is Engine
    assert (
        session_store.Session
        is engine_runtime.Session
        is application.Session
        is Session
    )
    assert (
        engine_runtime.iter_turn
        is follow_up_memory_writer.iter_turn
        is application.iter_turn
        is bridge.iter_turn
    )
    assert (
        lesson_entry.GatewayModel
        is provider.GatewayModel
        is application.GatewayModel
        is markdownflow_model.GatewayModel
    )
    assert markdownflow_model.turn_stop_requested is bridge.turn_stop_requested
