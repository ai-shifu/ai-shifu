"""Access current learner variables through their existing storage and services.

The runtime facade delegates to the profile service, preserving canonical user fields and the
caller's transaction. Values can come from course interactions or settings; no origin is tracked.
The broad reader exposes ``var_variable_values`` across courses and keeps other courses in
``elsewhere``.

Two facts about that table shape everything here:

* Changed values append rows; identical saves can reuse the selected row. The newest live row
  for a `(user, scope, key)` wins, and newest means the largest `id` (`created_at` is
  second-resolution and collides inside one flush).
* Scope is expressed by `shifu_bid`: a course id, or `""` for the global scope the system
  variables use. There is no scope column.
"""

from flaskr.service.learn.memory.facade import (
    load_course_variables,
    stage_course_variables,
)
from flaskr.service.learn.memory.reader import (
    LearnerMemory,
    MemoryEntry,
    load_learner_memory,
)

__all__ = [
    "LearnerMemory",
    "MemoryEntry",
    "load_course_variables",
    "load_learner_memory",
    "stage_course_variables",
]
