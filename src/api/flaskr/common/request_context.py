"""Propagate request identity across execution contexts."""

import threading

thread_local = threading.local()
