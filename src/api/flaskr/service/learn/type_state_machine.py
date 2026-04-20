"""Unified state machine for producing ``RunElementSSEMessageDTO.type``.

The state machine replaces ad-hoc string concatenation scattered across
writer branches. All ``type`` values emitted to the SSE stream MUST be
produced by this module.

State definitions
-----------------
- ``IDLE``       – no open element
- ``BUILDING``   – accumulating a new element
- ``PATCHING``   – applying incremental update to an existing element (``is_new=false``)
- ``TERMINATED`` – final state after ``done`` / ``error``

See design doc §3.4 for the full transition table.
"""

from __future__ import annotations

from enum import Enum


class TypeState(Enum):
    IDLE = "IDLE"
    BUILDING = "BUILDING"
    PATCHING = "PATCHING"
    TERMINATED = "TERMINATED"


class TypeInput(Enum):
    """Trigger events fed into the state machine."""

    CONTENT_START = "content_start"
    INCREMENTAL_UPDATE = "incremental_update"
    BLOCK_BREAK = "block_break"
    AUDIO_SEGMENT = "audio_segment"
    AUDIO_COMPLETE = "audio_complete"
    DONE = "done"
    ERROR = "error"


# Output ``type`` strings emitted for each transition.
TYPE_ELEMENT = "element"
TYPE_BREAK = "break"
TYPE_AUDIO_SEGMENT = "audio_segment"
TYPE_AUDIO_COMPLETE = "audio_complete"
TYPE_DONE = "done"
TYPE_ERROR = "error"


class TypeStateMachine:
    """Pure-logic state machine that produces the SSE ``type`` field.

    Usage::

        sm = TypeStateMachine()
        out_type = sm.feed(TypeInput.CONTENT_START)
        # out_type == "element", sm.state == TypeState.BUILDING
    """

    def __init__(self) -> None:
        self._state = TypeState.IDLE

    @property
    def state(self) -> TypeState:
        return self._state

    @property
    def is_terminated(self) -> bool:
        return self._state is TypeState.TERMINATED

    def feed(self, trigger: TypeInput, *, is_new: bool = True) -> str:
        """Process *trigger* and return the ``type`` string for the SSE message.

        Parameters
        ----------
        trigger:
            The input event.
        is_new:
            Only inspected when *trigger* is ``CONTENT_START``.  When ``False``
            the machine transitions to ``PATCHING`` instead of ``BUILDING``.

        Returns
        -------
        str
            The ``type`` value to embed in ``RunElementSSEMessageDTO``.

        Raises
        ------
        ValueError
            If the transition is illegal (e.g. feeding after ``TERMINATED``).
        """
        if self._state is TypeState.TERMINATED:
            raise ValueError(
                f"State machine already terminated; cannot process {trigger!r}"
            )

        if trigger is TypeInput.CONTENT_START:
            if is_new:
                self._state = TypeState.BUILDING
            else:
                self._state = TypeState.PATCHING
            return TYPE_ELEMENT

        if trigger is TypeInput.INCREMENTAL_UPDATE:
            self._state = TypeState.PATCHING
            return TYPE_ELEMENT

        if trigger is TypeInput.BLOCK_BREAK:
            self._state = TypeState.IDLE
            return TYPE_BREAK

        if trigger is TypeInput.AUDIO_SEGMENT:
            # Audio events do not change the element state.
            return TYPE_AUDIO_SEGMENT

        if trigger is TypeInput.AUDIO_COMPLETE:
            return TYPE_AUDIO_COMPLETE

        if trigger is TypeInput.DONE:
            self._state = TypeState.TERMINATED
            return TYPE_DONE

        if trigger is TypeInput.ERROR:
            self._state = TypeState.TERMINATED
            return TYPE_ERROR

        raise ValueError(f"Unknown trigger: {trigger!r}")  # pragma: no cover

    def reset(self) -> None:
        """Reset the machine to ``IDLE``."""
        self._state = TypeState.IDLE
