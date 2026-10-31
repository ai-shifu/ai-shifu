"""Follow-up questions asked beside a lesson, independent of the engine that teaches it.

The package init stays import-free: shifu settings import provider constants
from ``ask.providers`` and must not pull in the follow-up runtime, which in turn
imports shifu modules. Import from the submodules directly.
"""
