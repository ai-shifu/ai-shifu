"""Moved to :mod:`flaskr.service.learn.ask.provider_langfuse`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.ask import provider_langfuse

sys.modules[__name__] = provider_langfuse
