"""Reading what a learner has told us, across the courses they have taken.

The values themselves live where they always have: `var_variable_values`, written by the profile
service during a lesson. This package only reads them, and it exists because nothing else does it
this way -- every existing reader is scoped to one course.

Two facts about that table shape everything here:

* It is **append-only**. Answering the same question again adds a row; the newest row for a
  `(user, scope, key)` wins, and newest means the largest `id` (`created_at` is second-resolution
  and collides inside one flush).
* Scope is expressed by `shifu_bid`: a course id, or `""` for the global scope the system
  variables use. There is no scope column.
"""

from flaskr.service.learn.memory.reader import (
    LearnerMemory,
    MemoryEntry,
    load_learner_memory,
)

__all__ = ["LearnerMemory", "MemoryEntry", "load_learner_memory"]
