"""Moved to :mod:`flaskr.service.learn.elements.factory`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import factory

sys.modules[__name__] = factory
