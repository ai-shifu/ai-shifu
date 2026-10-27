"""Moved to :mod:`flaskr.service.learn.elements.payloads`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import payloads

sys.modules[__name__] = payloads
