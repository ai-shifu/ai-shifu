"""Moved to :mod:`flaskr.service.learn.elements.rows`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import rows

sys.modules[__name__] = rows
