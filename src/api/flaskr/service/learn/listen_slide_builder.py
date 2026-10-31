"""Moved to :mod:`flaskr.service.learn.elements.slide_builder`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import slide_builder

sys.modules[__name__] = slide_builder
