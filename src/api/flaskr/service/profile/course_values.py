"""Moved to :mod:`flaskr.service.memory.course_values`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.memory import course_values

sys.modules[__name__] = course_values
