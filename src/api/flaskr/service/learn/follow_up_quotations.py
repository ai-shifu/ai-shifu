"""Moved to :mod:`flaskr.service.learn.ask.quotations`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import quotations

sys.modules[__name__] = quotations
