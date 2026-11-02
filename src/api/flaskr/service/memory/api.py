"""Stable public entry points for cross-service learner memory operations."""

from flaskr.service.memory.course_memory import (
    course_memory_deletion_state,
    course_memory_value_versions,
    delete_course_memory,
    list_course_memory,
)
from flaskr.service.memory.course_references import (
    COURSE_REFERENCE_PREFIX,
    SHARED_ANSWER_PREFIX,
    is_course_reference,
)
from flaskr.service.memory.course_values import get_user_profiles, save_user_profiles
from flaskr.service.memory.dtos import (
    MemorySnapshot,
    MemoryUpdate,
    VariableMemoryUpdate,
)
from flaskr.service.memory.facade import load_memory, stage_memory
from flaskr.service.memory.reader import (
    LearnerMemory,
    MemoryEntry,
    load_course_variables,
    load_learner_memory,
)
from flaskr.service.memory.settings_writer import update_user_profile_with_lable

__all__ = [
    "COURSE_REFERENCE_PREFIX",
    "SHARED_ANSWER_PREFIX",
    "LearnerMemory",
    "MemoryEntry",
    "MemorySnapshot",
    "MemoryUpdate",
    "VariableMemoryUpdate",
    "course_memory_deletion_state",
    "course_memory_value_versions",
    "delete_course_memory",
    "get_user_profiles",
    "is_course_reference",
    "list_course_memory",
    "load_course_variables",
    "load_learner_memory",
    "load_memory",
    "save_user_profiles",
    "stage_memory",
    "update_user_profile_with_lable",
]
