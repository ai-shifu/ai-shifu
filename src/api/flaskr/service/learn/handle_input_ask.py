"""Moved to :mod:`flaskr.service.learn.ask.handler`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import handler

sys.modules[__name__] = handler
