"""Serialize provider work for one business order with a renewable lock."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from flaskr.service.common.models import raise_error
from flaskr.service.order.funs_lookup import order_funs

_payment_lock_ownership_events: ContextVar[tuple[threading.Event, ...]] = ContextVar(
    "payment_lock_ownership_events", default=()
)


def _assert_payment_lifecycle_lock_owned() -> None:
    if any(event.is_set() for event in _payment_lock_ownership_events.get()):
        raise_error("server.order.orderStatusError")


class _RenewablePaymentLock(Protocol):
    def extend(self, seconds: int, *, replace_ttl: bool) -> bool: ...

    def release(self) -> None: ...


class _PaymentLifecycleLease:
    """Manage renewal and checked release for one payment lifecycle lock."""

    def __init__(self, lock: _RenewablePaymentLock) -> None:
        self._lock = lock
        self._stop_renewal = threading.Event()
        self.ownership_lost = threading.Event()
        self._released = False
        self._renewal = threading.Thread(target=self._renew_lease, daemon=True)
        self._renewal.start()

    def _renew_lease(self) -> None:
        while not self._stop_renewal.wait(20):
            try:
                if not self._lock.extend(60, replace_ttl=True):
                    self.ownership_lost.set()
                    return
            except Exception:
                self.ownership_lost.set()
                return

    def release_checked(self) -> None:
        """Release the lease and fail when Redis reports lost ownership."""
        if self._released:
            return
        self._released = True
        self._stop_renewal.set()
        self._renewal.join(timeout=1)
        try:
            self._lock.release()
        except Exception:
            self.ownership_lost.set()
        if self.ownership_lost.is_set():
            raise_error("server.order.orderStatusError")


@contextmanager
def payment_lifecycle_lock(order_bid: str) -> Iterator[_PaymentLifecycleLease]:
    """Serialize external provider work that belongs to one business order."""
    lock = order_funs.cache_provider.lock(
        f"order-payment-lifecycle:{order_bid}",
        timeout=60,
        blocking_timeout=60,
        thread_local=False,
    )
    if not lock or not lock.acquire(blocking=True):
        raise_error("server.order.orderStatusError")
    lease = _PaymentLifecycleLease(lock)
    ownership_token = _payment_lock_ownership_events.set(
        (*_payment_lock_ownership_events.get(), lease.ownership_lost)
    )
    try:
        yield lease
    finally:
        try:
            lease.release_checked()
        finally:
            _payment_lock_ownership_events.reset(ownership_token)
