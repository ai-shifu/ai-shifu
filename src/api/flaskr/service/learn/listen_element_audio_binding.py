"""Moved to :mod:`flaskr.service.learn.elements.audio_binding`; this alias keeps the old import path for one release."""

import sys

from flaskr.service.learn.elements import audio_binding

sys.modules[__name__] = audio_binding
