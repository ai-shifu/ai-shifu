"""Moved to :mod:`flaskr.service.memory.course_references`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.memory import course_references

sys.modules[__name__] = course_references
