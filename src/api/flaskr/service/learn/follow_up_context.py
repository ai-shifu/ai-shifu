"""Moved to :mod:`flaskr.service.learn.ask.context`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import context

sys.modules[__name__] = context
