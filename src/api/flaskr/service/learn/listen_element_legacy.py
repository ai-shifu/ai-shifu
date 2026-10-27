"""Moved to :mod:`flaskr.service.learn.elements.legacy`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import legacy

sys.modules[__name__] = legacy
