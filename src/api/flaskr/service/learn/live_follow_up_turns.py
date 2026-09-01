"""Turn-oriented transcript reconciliation for Gemini Live follow-up."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from flaskr.service.learn.gemini_live_provider import GeminiLiveServerEvent

LiveTranscriptRole = Literal["user", "assistant"]
LiveTurnTerminalReason = Literal["turn_complete", "interrupted", "session_end"]


@dataclass(frozen=True)
class LiveTranscriptUpdate:
    """A stable transcript update suitable for the browser control channel."""

    role: LiveTranscriptRole
    turn_index: int
    text: str
    final: bool


@dataclass(frozen=True)
class LiveTurnIngestResult:
    """Actions produced by one normalized Gemini server event."""

    turn_index: int
    audio_turn_index: int | None
    audio_chunks: tuple[bytes, ...]
    transcript_updates: tuple[LiveTranscriptUpdate, ...]
    interrupted_turn_index: int | None = None
    terminal_turn_index: int | None = None


@dataclass(frozen=True)
class LiveTurnCommit:
    """Immutable turn data ready for idempotent persistence."""

    session_bid: str
    turn_index: int
    user_transcript: str
    answer_transcript: str
    full_answer_transcript: str
    interrupted: bool
    terminal_reason: LiveTurnTerminalReason
    usage_metadata: dict[str, object] | None
    audio_sent_bytes: int
    audio_played_bytes: int

    @property
    def has_final_user_transcript(self) -> bool:
        """Return whether this turn may create ASK/ANSWER history."""
        return bool(self.user_transcript)


@dataclass
class _OutputCheckpoint:
    byte_count: int
    text: str


@dataclass
class _PendingOutputCheckpoint:
    remaining_bytes: int
    text: str


@dataclass
class _TurnState:
    turn_index: int
    user_transcript: str = ""
    user_interim_transcript: str = ""
    user_input_transcription_received: bool = False
    user_transcript_final: bool = False
    output_transcript: str = ""
    output_transcript_waiting_for_audio: str = ""
    output_checkpoints: list[_OutputCheckpoint] = field(default_factory=list)
    pending_output_checkpoints: list[_PendingOutputCheckpoint] = field(
        default_factory=list
    )
    audio_sent_bytes: int = 0
    audio_played_bytes: int = 0
    playback_complete: bool = False
    usage_metadata: dict[str, object] | None = None
    terminal_reason: LiveTurnTerminalReason | None = None
    terminal_at: float | None = None
    ready_at: float | None = None

    @property
    def has_activity(self) -> bool:
        """Return whether a turn has data worth reconciling or metering."""
        return bool(
            self.user_transcript
            or self.output_transcript
            or self.audio_sent_bytes
            or self.usage_metadata is not None
        )


class LiveTurnAccumulator:
    """Aggregate Gemini events into bounded, playback-aware turns.

    Gemini sends input/output transcription independently from audio and may
    deliver a final transcript fragment just after ``turnComplete``. Terminal
    turns therefore remain mutable for a bounded reconciliation window. Audio
    delivery and browser playback are explicit calls so a failed browser send
    is never mistaken for audio the learner heard.
    """

    def __init__(
        self,
        session_bid: str,
        *,
        start_turn_index: int = 1,
        reconciliation_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create an accumulator for one browser Live session."""
        if not session_bid:
            message = "Live session BID is required"
            raise ValueError(message)
        if start_turn_index < 0:
            message = "Live turn index cannot be negative"
            raise ValueError(message)
        if reconciliation_seconds < 0:
            message = "Live reconciliation window cannot be negative"
            raise ValueError(message)
        self.session_bid = session_bid
        self.reconciliation_seconds = reconciliation_seconds
        self._clock = clock
        self._active_turn_index = start_turn_index
        self._turns: dict[int, _TurnState] = {}
        self._last_response_turn_index: int | None = None
        self._interrupted_turns_awaiting_completion: list[int] = []
        self._lock = threading.RLock()

    @property
    def active_turn_index(self) -> int:
        """Return the turn currently receiving learner transcription."""
        with self._lock:
            return self._active_turn_index

    def ingest_event(
        self,
        event: GeminiLiveServerEvent,
        *,
        now: float | None = None,
    ) -> LiveTurnIngestResult:
        """Apply one Gemini event and return browser-facing incremental data."""
        observed_at = self._clock() if now is None else now
        with self._lock:
            updates: list[LiveTranscriptUpdate] = []
            trailing_interrupted_turn_index = (
                self._interrupted_turns_awaiting_completion[0]
                if event.turn_complete
                and not event.interrupted
                and self._interrupted_turns_awaiting_completion
                else None
            )
            trailing_interrupted_state = (
                self._turns.get(trailing_interrupted_turn_index)
                if trailing_interrupted_turn_index is not None
                else None
            )
            input_state = None
            if not event.interrupted:
                input_state = self._select_input_state(
                    event.input_transcripts,
                    observed_at=observed_at,
                )
            if trailing_interrupted_state is not None:
                # Gemini sends ``interrupted`` and then a trailing
                # ``turnComplete`` for the same old response. New user
                # transcription may already belong to the next active turn,
                # while output/usage on this terminal message still belongs to
                # the interrupted response.
                response_state = trailing_interrupted_state
            else:
                response_state = (
                    input_state
                    if event.input_transcripts and input_state is not None
                    else self._select_response_state(observed_at=observed_at)
                )
            response_touched = bool(
                event.output_transcripts
                or event.audio_chunks
                or event.usage_metadata is not None
            )

            updates.extend(
                self._transcript_update(
                    response_state,
                    role="assistant",
                    final=response_state.terminal_reason is not None,
                )
                for fragment in event.output_transcripts
                if self._merge_output(
                    response_state,
                    fragment,
                    defer_checkpoint=bool(event.audio_chunks),
                )
            )
            if event.output_transcripts and event.audio_chunks:
                pending_bytes = sum(len(chunk) for chunk in event.audio_chunks)
                if pending_bytes and response_state.output_transcript.strip():
                    response_state.pending_output_checkpoints.append(
                        _PendingOutputCheckpoint(
                            remaining_bytes=pending_bytes,
                            text=response_state.output_transcript.strip(),
                        )
                    )
            if event.audio_chunks:
                self._last_response_turn_index = response_state.turn_index
            if event.usage_metadata is not None:
                response_state.usage_metadata = dict(event.usage_metadata)

            interrupted_turn_index = None
            terminal_turn_index = None
            if event.interrupted:
                terminal_state = self._terminal_target(response_state)
                self._mark_terminal(
                    terminal_state,
                    reason="interrupted",
                    observed_at=observed_at,
                )
                interrupted_turn_index = terminal_state.turn_index
                terminal_turn_index = terminal_state.turn_index
                updates.extend(self._final_updates(terminal_state))
                self._advance_after_terminal(terminal_state)
                if not event.turn_complete:
                    self._interrupted_turns_awaiting_completion.append(
                        terminal_state.turn_index
                    )

            if input_state is None:
                input_state = self._active_state()
            updates.extend(
                self._transcript_update(
                    input_state,
                    role="user",
                    final=input_state.terminal_reason is not None,
                )
                for fragment in event.input_transcripts
                if self._merge_input(input_state, fragment)
            )
            if not event.input_transcripts:
                interim_text = _latest_transcript_snapshot(
                    event.interim_input_transcripts
                )
                if interim_text and self._replace_input_interim(
                    input_state,
                    interim_text,
                ):
                    updates.append(
                        LiveTranscriptUpdate(
                            role="user",
                            turn_index=input_state.turn_index,
                            text=interim_text,
                            final=False,
                        )
                    )

            if trailing_interrupted_turn_index is not None:
                self._interrupted_turns_awaiting_completion.pop(0)
            elif event.turn_complete and not event.interrupted:
                terminal_state = self._terminal_target(
                    response_state if response_touched else input_state
                )
                if terminal_state.has_activity:
                    self._mark_terminal(
                        terminal_state,
                        reason="turn_complete",
                        observed_at=observed_at,
                    )
                    terminal_turn_index = terminal_state.turn_index
                    updates.extend(self._final_updates(terminal_state))
                    self._advance_after_terminal(terminal_state)

            audio_turn_index = response_state.turn_index if event.audio_chunks else None
            return LiveTurnIngestResult(
                turn_index=self._active_turn_index,
                audio_turn_index=audio_turn_index,
                audio_chunks=event.audio_chunks,
                transcript_updates=tuple(updates),
                interrupted_turn_index=interrupted_turn_index,
                terminal_turn_index=terminal_turn_index,
            )

    def process_event(
        self,
        event: GeminiLiveServerEvent,
        *,
        now: float | None = None,
    ) -> LiveTurnIngestResult:
        """Route-friendly alias for applying one Gemini event."""
        return self.ingest_event(event, now=now)

    def record_audio_sent(self, turn_index: int, byte_count: int) -> int:
        """Record PCM bytes successfully forwarded to the browser."""
        if byte_count < 0:
            message = "Live audio byte count cannot be negative"
            raise ValueError(message)
        with self._lock:
            state = self._turns.get(turn_index)
            if state is None:
                state = self._state(turn_index)
            if byte_count == 0:
                return state.audio_sent_bytes
            self._consume_sent_audio(state, byte_count)
            return state.audio_sent_bytes

    def finish_audio_event(self, turn_index: int) -> None:
        """Bind an earlier independent transcript to this complete audio event.

        Gemini may deliver output transcription before the corresponding audio
        in a separate server message. Waiting until every chunk from the next
        audio event has been forwarded keeps the playback checkpoint
        conservative without dropping a fully played answer solely because of
        that documented cross-message reordering.
        """
        with self._lock:
            state = self._turns.get(turn_index)
            if (
                state is None
                or not state.output_transcript_waiting_for_audio
                or state.audio_sent_bytes <= 0
            ):
                return
            self._upsert_output_checkpoint(
                state,
                text=state.output_transcript_waiting_for_audio,
            )
            state.output_transcript_waiting_for_audio = ""

    def record_playback_progress(self, turn_index: int, played_bytes: int) -> int:
        """Record the browser's absolute, monotonic played-byte watermark."""
        if played_bytes < 0:
            message = "Live playback byte count cannot be negative"
            raise ValueError(message)
        with self._lock:
            state = self._turns.get(turn_index)
            if state is None:
                return 0
            bounded = min(played_bytes, state.audio_sent_bytes)
            state.audio_played_bytes = max(state.audio_played_bytes, bounded)
            return state.audio_played_bytes

    def mark_playback_complete(self, turn_index: int) -> int:
        """Advance playback to all bytes sent for a completed browser queue."""
        with self._lock:
            state = self._turns.get(turn_index)
            if state is None:
                return 0
            state.audio_played_bytes = state.audio_sent_bytes
            state.playback_complete = True
            return state.audio_played_bytes

    def ready_at(self, turn_index: int) -> float | None:
        """Return the terminal reconciliation deadline for a turn."""
        with self._lock:
            state = self._turns.get(turn_index)
            return state.ready_at if state is not None else None

    def pop_ready(
        self,
        *,
        now: float | None = None,
        force: bool = False,
    ) -> list[LiveTurnCommit]:
        """Remove terminal turns whose bounded reconciliation window elapsed."""
        observed_at = self._clock() if now is None else now
        with self._lock:
            ready_indexes = [
                turn_index
                for turn_index, state in self._turns.items()
                if state.terminal_reason is not None
                and (force or state.ready_at is None or state.ready_at <= observed_at)
                and (force or self._playback_is_settled(state))
            ]
            commits: list[LiveTurnCommit] = []
            for turn_index in sorted(ready_indexes):
                state = self._turns.pop(turn_index)
                self._interrupted_turns_awaiting_completion = [
                    pending_turn_index
                    for pending_turn_index in self._interrupted_turns_awaiting_completion
                    if pending_turn_index != turn_index
                ]
                commits.append(self._to_commit(state))
                if self._last_response_turn_index == turn_index:
                    self._last_response_turn_index = None
            return commits

    def finish_session(
        self,
        *,
        now: float | None = None,
    ) -> list[LiveTurnCommit]:
        """Finalize active data and return all pending turns immediately."""
        observed_at = self._clock() if now is None else now
        with self._lock:
            active = self._active_state()
            if active.has_activity and active.terminal_reason is None:
                self._mark_terminal(
                    active,
                    reason="session_end",
                    observed_at=observed_at,
                )
                self._advance_after_terminal(active)
            return self.pop_ready(now=observed_at, force=True)

    def _active_state(self) -> _TurnState:
        return self._state(self._active_turn_index)

    def _state(self, turn_index: int) -> _TurnState:
        state = self._turns.get(turn_index)
        if state is None:
            state = _TurnState(turn_index=turn_index)
            self._turns[turn_index] = state
        return state

    def _select_response_state(self, *, observed_at: float) -> _TurnState:
        active = self._active_state()
        if active.has_activity:
            return active
        previous = self._latest_mutable_terminal(observed_at=observed_at)
        if previous is not None:
            return previous
        return active

    def _select_input_state(
        self,
        fragments: tuple[str, ...],
        *,
        observed_at: float,
    ) -> _TurnState:
        active = self._active_state()
        if not fragments or active.has_activity:
            return active
        previous = self._latest_mutable_terminal(observed_at=observed_at)
        if previous is None:
            return active
        if _transcript_fragments_reconcile(previous.user_transcript, fragments):
            return previous
        return active

    def _latest_mutable_terminal(
        self,
        *,
        observed_at: float,
    ) -> _TurnState | None:
        if self._last_response_turn_index is None:
            return None
        previous = self._turns.get(self._last_response_turn_index)
        if (
            previous is None
            or previous.terminal_reason is None
            or previous.ready_at is None
            or previous.ready_at < observed_at
        ):
            return None
        return previous

    def _terminal_target(self, candidate: _TurnState) -> _TurnState:
        return candidate

    def _advance_after_terminal(self, state: _TurnState) -> None:
        self._last_response_turn_index = state.turn_index
        if state.turn_index >= self._active_turn_index:
            self._active_turn_index = state.turn_index + 1

    def _mark_terminal(
        self,
        state: _TurnState,
        *,
        reason: LiveTurnTerminalReason,
        observed_at: float,
    ) -> None:
        if state.terminal_reason is None:
            state.terminal_reason = reason
            if reason != "session_end" and state.user_transcript.strip():
                state.user_transcript_final = True
            state.terminal_at = observed_at
            state.ready_at = observed_at + self.reconciliation_seconds
            return
        if reason == "interrupted":
            state.terminal_reason = reason

    @staticmethod
    def _merge_input(state: _TurnState, fragment: str) -> bool:
        state.user_input_transcription_received = True
        state.user_interim_transcript = ""
        merged = merge_live_transcript(state.user_transcript, fragment)
        if merged == state.user_transcript:
            return False
        state.user_transcript = merged
        if state.terminal_reason in {"turn_complete", "interrupted"}:
            state.user_transcript_final = True
        return True

    @staticmethod
    def _replace_input_interim(state: _TurnState, transcript: str) -> bool:
        if state.user_input_transcription_received:
            return False
        normalized = transcript.strip()
        if not normalized or normalized == state.user_interim_transcript:
            return False
        state.user_interim_transcript = normalized
        return True

    def _merge_output(
        self,
        state: _TurnState,
        fragment: str,
        *,
        defer_checkpoint: bool,
    ) -> bool:
        merged = merge_live_transcript(state.output_transcript, fragment)
        if merged == state.output_transcript:
            return False
        state.output_transcript = merged
        self._last_response_turn_index = state.turn_index
        if defer_checkpoint:
            # The caller will attach this transcript after every audio chunk
            # carried by the same server event has been forwarded.
            state.output_transcript_waiting_for_audio = ""
        elif state.audio_sent_bytes:
            self._upsert_output_checkpoint(state)
            state.output_transcript_waiting_for_audio = ""
        else:
            state.output_transcript_waiting_for_audio = merged.strip()
        return True

    def _consume_sent_audio(self, state: _TurnState, byte_count: int) -> None:
        state.playback_complete = False
        cursor = state.audio_sent_bytes
        state.audio_sent_bytes += byte_count
        remaining = byte_count
        while remaining and state.pending_output_checkpoints:
            pending = state.pending_output_checkpoints[0]
            consumed = min(remaining, pending.remaining_bytes)
            cursor += consumed
            remaining -= consumed
            pending.remaining_bytes -= consumed
            if pending.remaining_bytes:
                continue
            self._upsert_output_checkpoint(
                state,
                byte_count=cursor,
                text=pending.text,
            )
            state.pending_output_checkpoints.pop(0)

    @staticmethod
    def _playback_is_settled(state: _TurnState) -> bool:
        if state.terminal_reason == "interrupted" or state.audio_sent_bytes == 0:
            return True
        return state.playback_complete or (
            state.audio_played_bytes >= state.audio_sent_bytes
        )

    @staticmethod
    def _upsert_output_checkpoint(
        state: _TurnState,
        *,
        byte_count: int | None = None,
        text: str | None = None,
    ) -> None:
        normalized_text = (text or state.output_transcript).strip()
        resolved_byte_count = (
            state.audio_sent_bytes if byte_count is None else byte_count
        )
        if not normalized_text:
            return
        if (
            state.output_checkpoints
            and state.output_checkpoints[-1].byte_count == resolved_byte_count
        ):
            state.output_checkpoints[-1].text = normalized_text
            return
        state.output_checkpoints.append(
            _OutputCheckpoint(
                byte_count=resolved_byte_count,
                text=normalized_text,
            )
        )

    @staticmethod
    def _transcript_update(
        state: _TurnState,
        *,
        role: LiveTranscriptRole,
        final: bool,
    ) -> LiveTranscriptUpdate:
        text = state.user_transcript if role == "user" else state.output_transcript
        return LiveTranscriptUpdate(
            role=role,
            turn_index=state.turn_index,
            text=text.strip(),
            final=final,
        )

    def _final_updates(self, state: _TurnState) -> list[LiveTranscriptUpdate]:
        updates: list[LiveTranscriptUpdate] = []
        if state.user_transcript.strip():
            updates.append(self._transcript_update(state, role="user", final=True))
        if state.output_transcript.strip():
            updates.append(self._transcript_update(state, role="assistant", final=True))
        return updates

    def _to_commit(self, state: _TurnState) -> LiveTurnCommit:
        terminal_reason = state.terminal_reason
        if terminal_reason is None:
            message = "Cannot commit a non-terminal Live turn"
            raise RuntimeError(message)
        played_answer = ""
        for checkpoint in state.output_checkpoints:
            if checkpoint.byte_count > state.audio_played_bytes:
                break
            played_answer = checkpoint.text
        return LiveTurnCommit(
            session_bid=self.session_bid,
            turn_index=state.turn_index,
            user_transcript=(
                state.user_transcript.strip() if state.user_transcript_final else ""
            ),
            answer_transcript=played_answer,
            full_answer_transcript=state.output_transcript.strip(),
            interrupted=terminal_reason == "interrupted",
            terminal_reason=terminal_reason,
            usage_metadata=(
                dict(state.usage_metadata) if state.usage_metadata is not None else None
            ),
            audio_sent_bytes=state.audio_sent_bytes,
            audio_played_bytes=state.audio_played_bytes,
        )


def merge_live_transcript(current: str, incoming: str) -> str:
    """Merge cumulative, delta, stale-prefix, and overlapping transcripts."""
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming == current or current.startswith(incoming):
        return current
    if incoming.startswith(current) or incoming.endswith(current):
        return incoming

    maximum_overlap = min(len(current), len(incoming))
    for overlap in range(maximum_overlap, 0, -1):
        if current[-overlap:] == incoming[:overlap]:
            return current + incoming[overlap:]
    return current + incoming


def _transcript_fragments_reconcile(
    current: str,
    fragments: tuple[str, ...],
) -> bool:
    if not current:
        return True
    merged = current
    for fragment in fragments:
        if not _transcript_fragment_reconciles(merged, fragment):
            return False
        merged = merge_live_transcript(merged, fragment)
    return True


def _latest_transcript_snapshot(fragments: tuple[str, ...]) -> str:
    for fragment in reversed(fragments):
        normalized = fragment.strip()
        if normalized:
            return normalized
    return ""


def _transcript_fragment_reconciles(current: str, incoming: str) -> bool:
    if not incoming or not current:
        return True
    if (
        incoming.startswith(current)
        or current.startswith(incoming)
        or incoming.endswith(current)
        or incoming[0].isspace()
    ):
        return True
    maximum_overlap = min(len(current), len(incoming))
    return any(
        current[-overlap:] == incoming[:overlap]
        for overlap in range(maximum_overlap, 0, -1)
    )
