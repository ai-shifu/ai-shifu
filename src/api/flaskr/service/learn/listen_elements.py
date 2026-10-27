"""Moved to :mod:`flaskr.service.learn.elements.run_adapter`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import run_adapter

sys.modules[__name__] = run_adapter
