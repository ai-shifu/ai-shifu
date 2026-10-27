"""Moved to :mod:`flaskr.service.learn.elements.run_stream`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import run_stream

sys.modules[__name__] = run_stream
