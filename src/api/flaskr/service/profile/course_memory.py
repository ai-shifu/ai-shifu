"""Moved to :mod:`flaskr.service.memory.course_memory`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.memory import course_memory

sys.modules[__name__] = course_memory
