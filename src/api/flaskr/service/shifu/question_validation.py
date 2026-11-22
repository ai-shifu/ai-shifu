"""Keep course-authored questions out of the system variable namespace."""

from flaskr.service.common import raise_error
from flaskr.service.common.models import raise_error_with_args
from flaskr.service.shifu.consts import QUESTION_NAME_MAX_LENGTH
from markdownflow import MarkdownFlowDocument
from markdownflow.engine.script import collected_names
from markdownflow.syntax.variable_names import read_interaction_variable

QUESTION_NAME_PREVIEW_LENGTH = 20


def is_question_name_too_long(name: str) -> bool:
    """Whether a question exceeds the authored length limit in code points."""
    return len(name) > QUESTION_NAME_MAX_LENGTH


def assert_course_question_names_allowed(document: MarkdownFlowDocument) -> None:
    """Reject reserved question bindings while allowing system references."""
    for block in document.get_all_blocks():
        if not block.is_interaction:
            continue
        marker = read_interaction_variable(block.content[2:-1])
        if marker and marker.name and marker.name.startswith("sys_"):
            raise_error("server.profile.keyReserved")


def assert_course_question_names_within_limit(document: MarkdownFlowDocument) -> None:
    """Reject any {{ }} question longer than the authored length limit.

    Draft saves skip this check so autosave never discards an author's text;
    publish and import enforce it before content reaches learners.
    """
    for name in document.extract_variables():
        if is_question_name_too_long(name):
            preview = name[:QUESTION_NAME_PREVIEW_LENGTH]
            raise_error_with_args(
                "server.profile.keyTooLong",
                max_length=QUESTION_NAME_MAX_LENGTH,
                length=len(name),
                preview=preview,
            )


def assert_no_new_system_declarations(content: str, retained_content: str = "") -> None:
    """Refuse new system memory declarations while preserving retained ones."""
    system_keys = {key for key in collected_names(content) if key.startswith("sys_")}
    if system_keys and not system_keys.issubset(collected_names(retained_content)):
        raise_error("server.profile.keyReserved")
