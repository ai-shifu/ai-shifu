"""Moved to :mod:`flaskr.service.learn.elements.legacy_record_builder`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import legacy_record_builder

sys.modules[__name__] = legacy_record_builder
