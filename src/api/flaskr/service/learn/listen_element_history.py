"""Moved to :mod:`flaskr.service.learn.elements.history`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import history

sys.modules[__name__] = history
