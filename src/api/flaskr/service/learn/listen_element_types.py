"""Moved to :mod:`flaskr.service.learn.elements.element_types`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import element_types

sys.modules[__name__] = element_types
