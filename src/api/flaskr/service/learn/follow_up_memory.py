"""Moved to :mod:`flaskr.service.learn.ask.memory`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import memory

sys.modules[__name__] = memory
