"""Moved to :mod:`flaskr.service.learn.host.run`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.host import run

sys.modules[__name__] = run
