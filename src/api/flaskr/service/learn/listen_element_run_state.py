"""Moved to :mod:`flaskr.service.learn.elements.run_state`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import run_state

sys.modules[__name__] = run_state
