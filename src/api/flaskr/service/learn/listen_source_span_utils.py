"""Moved to :mod:`flaskr.service.learn.elements.source_spans`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import source_spans

sys.modules[__name__] = source_spans
