"""Moved to :mod:`flaskr.service.learn.elements.queries`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import queries

sys.modules[__name__] = queries
