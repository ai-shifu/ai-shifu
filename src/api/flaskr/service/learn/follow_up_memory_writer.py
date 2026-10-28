"""Moved to :mod:`flaskr.service.learn.ask.memory_writer`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import memory_writer

sys.modules[__name__] = memory_writer
