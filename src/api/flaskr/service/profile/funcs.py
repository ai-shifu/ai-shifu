"""Moved to :mod:`flaskr.service.memory.settings_writer`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.memory import settings_writer

sys.modules[__name__] = settings_writer
