"""Keep course-authored questions out of the system variable namespace."""

from flaskr.service.common import raise_error
from markdownflow import MarkdownFlowDocument
from markdownflow.engine.script import collected_names
from markdownflow.syntax.variable_names import read_interaction_variable


def assert_course_question_names_allowed(document: MarkdownFlowDocument) -> None:
    """Reject reserved question bindings while allowing system references."""
    for block in document.get_all_blocks():
        if not block.is_interaction:
            continue
        marker = read_interaction_variable(block.content[2:-1])
        if marker and marker.name and marker.name.startswith("sys_"):
            raise_error("server.profile.keyReserved")


def assert_no_new_system_declarations(content: str, retained_content: str = "") -> None:
    """Refuse new system memory declarations while preserving retained ones."""
    system_keys = {key for key in collected_names(content) if key.startswith("sys_")}
    if system_keys and not system_keys.issubset(collected_names(retained_content)):
        raise_error("server.profile.keyReserved")
