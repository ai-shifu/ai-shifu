"""Moved to :mod:`flaskr.service.learn.elements.matching`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import matching

sys.modules[__name__] = matching
