"""Close one lesson HTTP stream after its terminal message or natural exhaustion."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

MessageT = TypeVar("MessageT")
ChunkT = TypeVar("ChunkT")


def _is_terminal_done(message: object) -> bool:
    if isinstance(message, dict):
        message_type = message.get("type")
        terminal = message.get("is_terminal")
    else:
        message_type = getattr(message, "type", None)
        terminal = getattr(message, "is_terminal", None)
    return getattr(message_type, "value", message_type) == "done" and terminal is True


def stream_request(
    message_iter_factory: Callable[[], Iterator[MessageT]],
    *,
    render: Callable[[MessageT], ChunkT],
    terminal_event_factory: Callable[[], MessageT] | None = None,
    error_messages_factory: Callable[[Exception], Iterator[MessageT]] | None = None,
    on_disconnect: Callable[[BaseException], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Iterator[ChunkT]:
    """Share EOF, error, terminal-once and cancellation rules at serialization boundaries.

    Source and serialization failures become error messages. An exception injected by
    a disconnected consumer never becomes output or an artificial successful EOF.
    A terminal is ephemeral: callers construct it without persisting a lesson element.
    """

    def deferred_messages() -> Iterator[MessageT]:
        yield from message_iter_factory()

    source: Iterator[MessageT] = deferred_messages()
    sources = [source]
    recovering = False
    try:
        while cancelled is None or not cancelled():
            synthetic_terminal = False
            try:
                message = next(source)
            except StopIteration:
                if terminal_event_factory is None:
                    return
                if cancelled is not None and cancelled():
                    return
                message = terminal_event_factory()
                synthetic_terminal = True
            except Exception as exc:
                if error_messages_factory is None or recovering:
                    raise
                source = iter(error_messages_factory(exc))
                sources.append(source)
                recovering = True
                continue

            if cancelled is not None and cancelled():
                return
            try:
                chunk = render(message)
            except Exception as exc:
                if error_messages_factory is None or recovering:
                    raise
                source = iter(error_messages_factory(exc))
                sources.append(source)
                recovering = True
                continue

            try:
                yield chunk
            except GeneratorExit as exc:
                if on_disconnect is not None:
                    on_disconnect(exc)
                raise
            except (ConnectionError, OSError) as exc:
                if on_disconnect is not None:
                    on_disconnect(exc)
                return
            if synthetic_terminal or _is_terminal_done(message):
                return
    finally:
        for iterator in reversed(sources):
            close = getattr(iterator, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    close()
