"""Define constants for learning sessions."""

ROLE_TEACHER = 1
ROLE_STUDENT = 2
ROLE_UI = 3


# Re-export learn status constants for backward compatibility with tests and callers.
from flaskr.service.order.consts import (  # noqa: F401, E402
    LEARN_STATUS_BRANCH,
    LEARN_STATUS_COMPLETED,
    LEARN_STATUS_IN_PROGRESS,
    LEARN_STATUS_LOCKED,
    LEARN_STATUS_NOT_EXIST,
    LEARN_STATUS_NOT_STARTED,
    LEARN_STATUS_REFUND,
    LEARN_STATUS_RESET,
    LEARN_STATUS_UNAVAILABLE,
)

INPUT_TYPE_ASK = "ask"

CONTEXT_INTERACTION_NEXT = "_sys_next_chapter"
CONTEXT_INTERACTION_LESSON_FEEDBACK_SCORE = "sys_lesson_feedback_score"
