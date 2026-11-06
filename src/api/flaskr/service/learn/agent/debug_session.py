"""Keep editor debug conversations separate from learner and teacher previews."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager, nullcontext, suppress
from typing import TYPE_CHECKING

from flaskr.api.markdownflow import Session
from flaskr.common.cache_provider import (
    CacheUnavailableError,
    InMemoryCacheProvider,
    redis_cache,
)
from flaskr.dao import get_redis_client
from flaskr.service.common.models import raise_error
from flaskr.service.learn.agent.rewind import (
    RewindPlan,
    RewindUnavailableError,
    checkpoint_of,
    plan_turn_rewind,
    restore,
)
from flaskr.service.learn.learn_dtos import ElementType, RunElementSSEMessageDTO
from flaskr.service.learn.preview_elements import PreviewElementRunAdapter
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

    from flask import Flask
    from flaskr.service.learn.learn_dtos import PlaygroundPreviewRequest


# Local development keeps debug state in process; configured Redis never uses this cache.
cache = InMemoryCacheProvider()


@contextmanager
def _debug_cache_access() -> Iterator[None]:
    try:
        yield
    except (RedisError, CacheUnavailableError):
        raise_error("server.learn.debugServiceUnavailable")


class DebugSessionStore:
    """An expiring session for one editor run of a draft lesson."""

    # Authors leave the debug panel open while they edit the draft; reads refresh
    # this too, so only a session nobody touches for this long expires.
    TTL_SECONDS = 4 * 60 * 60

    def __init__(
        self,
        app: Flask,
        *,
        user_bid: str,
        shifu_bid: str,
        outline_bid: str,
        run_bid: str,
        follow_script_edits: bool = False,
    ) -> None:
        """Bind an opaque run ID to its teacher, course, and lesson.

        ``follow_script_edits`` lets an answer resume the conversation after the
        author edited the draft; the run then continues under the edited script.
        """
        identity = f"{user_bid}\0{shifu_bid}\0{outline_bid}\0{run_bid}"
        digest = hashlib.sha256(identity.encode()).hexdigest()
        prefix = app.config.get("REDIS_KEY_PREFIX", "ai-shifu")
        self._key = f"{prefix}:agent_debug:{digest}"
        self._request_bid: str | None = None
        self._request_generation: int | None = None
        self._committed_variables: str | None = None
        self._cache = redis_cache if get_redis_client() is not None else cache
        self._follow_script_edits = follow_script_edits

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        with _debug_cache_access():
            lock = self._cache.lock(
                f"{self._key}:write", timeout=10, blocking_timeout=10
            )
            acquired = lock.acquire(blocking=True, blocking_timeout=10)
        if not acquired:
            raise_error("server.learn.debugServiceUnavailable")
        try:
            yield
        except BaseException:
            # Cleanup must preserve the original business error or stream cancellation.
            with suppress(RedisError, CacheUnavailableError):
                lock.release()
            raise
        else:
            with _debug_cache_access():
                lock.release()

    def _assert_current_request(self) -> None:
        """Check the request fence while the caller holds the cache write lock."""
        if self._request_bid is None:
            return
        with _debug_cache_access():
            current = self._cache.get(f"{self._key}:request")
        if isinstance(current, bytes):
            current = current.decode()
        if current != self._request_bid:
            raise RewindUnavailableError

    def begin_request(self, *, generation: int | None = None) -> None:
        """Admit only a newer client request, independently of server scheduling."""
        request_bid = uuid.uuid4().hex
        with self._write_lock():
            with _debug_cache_access():
                current = self._cache.get(f"{self._key}:request")
                stored = self._cache.get(self._key)
            highest = 0
            for raw, field in ((current, "generation"), (stored, "request_generation")):
                try:
                    data = json.loads(raw) if raw else {}
                except (TypeError, ValueError):
                    data = {}
                value = data.get(field) if isinstance(data, dict) else None
                if isinstance(value, int):
                    highest = max(highest, value)
            if highest and (generation is None or generation <= highest):
                raise RewindUnavailableError
            # Keep order and ownership in one cache write. Legacy unsequenced
            # clients remain compatible until this session admits a sequenced run.
            token = (
                json.dumps({"request_bid": request_bid, "generation": generation})
                if generation is not None
                else request_bid
            )
            with _debug_cache_access():
                self._cache.setex(f"{self._key}:request", self.TTL_SECONDS, token)
            self._request_bid = token
            self._request_generation = generation

    def _payload(self, *, script: str, any_script: bool = False) -> dict | None:
        with _debug_cache_access():
            raw = self._cache.getex(self._key, ex=self.TTL_SECONDS)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict) or (
                not any_script
                and payload.get("script_hash")
                != hashlib.sha256(script.encode()).hexdigest()
            ):
                return None
        except (TypeError, ValueError):
            return None
        return payload

    def load(self, *, script: str) -> Session | None:
        """Resume when the editor is still debugging the same script.

        With ``follow_script_edits`` the stored conversation is returned even
        after the draft changed; the caller swaps in the edited script.
        """
        payload = self._payload(script=script, any_script=self._follow_script_edits)
        if payload is None:
            return None
        try:
            session = Session.loads(payload["session"])
        except (KeyError, TypeError, ValueError):
            # A deployment may replace the engine while this short-lived session is open.
            # An incompatible history is treated as expired, never replayed into a new turn.
            return None
        return session

    def save(
        self,
        session: Session,
        *,
        generated_block_bid: str = "",
        turn_record: str = "",
        rewind: RewindPlan | None = None,
        question_ids: list[str] | None = None,
        course_updates: dict[str, str] | None = None,
    ) -> None:
        """Save before the runner emits the turn's terminal event."""
        lock = self._write_lock() if self._request_bid is not None else nullcontext()
        with lock:
            self._assert_current_request()
            self._save(
                session,
                generated_block_bid=generated_block_bid,
                turn_record=turn_record,
                rewind=rewind,
                question_ids=question_ids,
            )
        if course_updates is not None:
            # Publish the session this request saved, even if a later request replaces
            # the cache entry before this turn's boundary reaches the adapter.
            self._committed_variables = json.dumps(
                {"variables": session.all_memory(), "course_updates": course_updates},
                ensure_ascii=False,
            )

    def take_committed_variables(self) -> str | None:
        """Consume this request's saved memory once, before its turn boundary."""
        snapshot = self._committed_variables
        self._committed_variables = None
        return snapshot

    def _save(
        self,
        session: Session,
        *,
        generated_block_bid: str,
        turn_record: str,
        rewind: RewindPlan | None,
        question_ids: list[str] | None,
    ) -> None:
        # Following a draft edit migrates the conversation, so its earlier turns keep
        # their checkpoints for later answer edits under the edited draft.
        previous = (
            self._payload(
                script=session.script.script, any_script=self._follow_script_edits
            )
            or {}
        )
        try:
            Session.loads(previous["session"])
        except (KeyError, TypeError, ValueError):
            # Only request ordering survives expiration of the stored conversation.
            previous = {"request_generation": previous.get("request_generation")}
        turns = previous.get("turns", [])
        if not isinstance(turns, list) or any(
            not isinstance(turn, dict) or not isinstance(turn.get("block_bid"), str)
            for turn in turns
        ):
            turns = []
        if rewind is not None:
            retired = set(rewind.retired_block_bids)
            turns = [turn for turn in turns if turn["block_bid"] not in retired]
        if generated_block_bid and turn_record:
            record = json.loads(turn_record)["agent_turn"]
            previous_turn = next(
                (turn for turn in turns if turn["block_bid"] == generated_block_bid), {}
            )
            turns = [turn for turn in turns if turn["block_bid"] != generated_block_bid]
            turns.append(
                {
                    **previous_turn,
                    "block_bid": generated_block_bid,
                    "record": record,
                    "question_ids": list(question_ids or []),
                }
            )
        payload = {
            "script_hash": hashlib.sha256(session.script.script.encode()).hexdigest(),
            "session": session.dumps(),
            "turns": turns,
        }
        generation = self._request_generation or previous.get("request_generation")
        if generation is not None:
            # Retain ordering for as long as the session lives, even if the
            # shorter-lived admission token expires before the saved session.
            payload["request_generation"] = generation
        encoded = json.dumps(payload)
        with _debug_cache_access():
            self._cache.setex(self._key, self.TTL_SECONDS, encoded)

    def bind_interactions(self, *, script: str, elements: dict[str, list[str]]) -> None:
        """Bind rendered controls to their emitted questions inside this owned run."""
        if not elements:
            return
        with self._write_lock():
            self._assert_current_request()
            payload = self._payload(script=script, any_script=self._follow_script_edits)
            if payload is None:
                raise RewindUnavailableError
            for turn in payload.get("turns", []):
                bids = elements.get(turn["block_bid"])
                if bids is not None:
                    turn["interaction_elements"] = list(bids)
            with _debug_cache_access():
                self._cache.setex(self._key, self.TTL_SECONDS, json.dumps(payload))

    def plan_rewind(
        self,
        *,
        script: str,
        block_bid: str,
        answering: bool = False,
        element_bid: str | None = None,
    ) -> RewindPlan:
        """Resolve storage ownership, then use the shared turn rewind rules."""
        payload = (
            self._payload(script=script, any_script=self._follow_script_edits) or {}
        )
        # Read session and checkpoints from one cache snapshot: the old stream
        # may still be saving while the replacement request is being admitted.
        try:
            session = Session.loads(payload["session"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RewindUnavailableError from exc
        turns = payload.get("turns", [])
        if not isinstance(turns, list) or any(
            not isinstance(turn, dict)
            or not isinstance(turn.get("block_bid"), str)
            or not isinstance(turn.get("record"), dict)
            for turn in turns
        ):
            raise RewindUnavailableError
        question_id = None
        resolved_block = block_bid
        if answering:
            if not element_bid:
                raise RewindUnavailableError
            # Exact element ownership matters when several controls share a block.
            owner = next(
                (
                    turn
                    for turn in turns
                    if element_bid in turn.get("interaction_elements", [])
                ),
                None,
            )
            if owner is None or block_bid not in {owner["block_bid"], element_bid}:
                raise RewindUnavailableError
            resolved_block = owner["block_bid"]
            offset = owner["interaction_elements"].index(element_bid)
            ids = owner.get("question_ids", [])
            if (
                not isinstance(ids, list)
                or offset >= len(ids)
                or any(not isinstance(q, str) or not q for q in ids)
            ):
                raise RewindUnavailableError
            question_id = ids[offset]
        plan = plan_turn_rewind(
            turns,
            block_bid=resolved_block,
            answering=answering,
            question_id=question_id,
        )
        if plan is None:
            # The old stream has not yet accepted this pending question. Claiming
            # this request fences its future save; answer from the retained state.
            if not session.pending or session.pending[0].tool_call_id != question_id:
                raise RewindUnavailableError
            checkpoint = checkpoint_of(session)
            checkpoint["user_memory"] = dict(session.user_memory)
            plan = RewindPlan(checkpoint=checkpoint, replay_values=None)
        if plan.checkpoint["messages"] > len(session.messages) or not isinstance(
            plan.checkpoint.get("user_memory"), dict
        ):
            raise RewindUnavailableError
        try:
            restore(session, plan.checkpoint)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RewindUnavailableError from exc
        return plan


def stream_debug_preview(
    app: Flask,
    *,
    preview_request: PlaygroundPreviewRequest,
    shifu_bid: str,
    outline_bid: str,
    user_bid: str,
    run_bid: str,
) -> Generator[RunElementSSEMessageDTO, None, None]:
    """Run the editor's draft through the existing 2.0 lesson and element pipeline."""
    from flaskr.service.learn.agent.lesson_entry import agent_lesson_events
    from flaskr.service.learn.agent.run_agent import learner_values

    script = preview_request.get_document()
    if not script.strip():
        msg = "Markdown-Flow content is empty"
        raise ValueError(msg)
    anchor = (
        preview_request.reload_element_bid or preview_request.reload_generated_block_bid
    )
    store = DebugSessionStore(
        app,
        user_bid=user_bid,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        run_bid=run_bid,
        # Authors edit the draft while debugging. Their next answer, or an edit of
        # an earlier answer, continues the conversation under the edited script
        # instead of discarding it.
        follow_script_edits=bool(preview_request.user_input or anchor),
    )
    session = store.load(script=script)
    if (preview_request.user_input or anchor) and session is None:
        raise_error("server.learn.debugSessionExpired")
    if anchor:
        try:
            rewind = store.plan_rewind(
                script=script,
                block_bid=preview_request.reload_generated_block_bid or anchor,
                answering=bool(learner_values(preview_request.user_input)),
                element_bid=preview_request.reload_element_bid,
            )
        except RewindUnavailableError:
            raise_error("server.learn.agentRewindUnavailable")
        restore(session, rewind.checkpoint)
        session.user_memory = dict(rewind.checkpoint["user_memory"])
    try:
        store.begin_request(generation=preview_request.request_generation)
    except RewindUnavailableError:
        raise_error("server.learn.agentRewindUnavailable")
    if anchor:
        yield RunElementSSEMessageDTO(
            type="debug_variables",
            event_type="debug_variables",
            content=json.dumps(session.all_memory(), ensure_ascii=False),
            is_terminal=False,
        )
    yield RunElementSSEMessageDTO(
        type="preview_engine",
        event_type="preview_engine",
        content="2.0",
        is_terminal=False,
    )
    adapter = PreviewElementRunAdapter(
        app,
        shifu_bid=shifu_bid,
        outline_bid=outline_bid,
        user_bid=user_bid,
        run_session_bid=run_bid,
    )
    messages = adapter.process(
        agent_lesson_events(
            app,
            user_bid=user_bid,
            shifu_bid=shifu_bid,
            outline_bid=outline_bid,
            user_input=preview_request.user_input,
            preview_mode=True,
            script_override=script,
            debug_store=store,
            preview_variables=preview_request.variables,
            reload_generated_block_bid=preview_request.reload_generated_block_bid,
            reload_element_bid=preview_request.reload_element_bid,
        )
    )
    interaction_elements: dict[str, list[str]] = {}
    for message in messages:
        element = message.content
        if (
            message.type == "element"
            and getattr(element, "element_type", None) == ElementType.INTERACTION
        ):
            bids = interaction_elements.setdefault(message.generated_block_bid, [])
            if element.element_bid not in bids:
                bids.append(element.element_bid)
                # Bind as soon as the control is shown, not at "done": a run stopped after
                # the turn saved but before "done" would otherwise leave the control
                # unowned, and editing that answer would be refused.
                store.bind_interactions(
                    script=script,
                    elements={message.generated_block_bid: list(bids)},
                )
        if anchor and message.type == "done":
            saved = store.load(script=script)
            if saved is not None:
                yield RunElementSSEMessageDTO(
                    type="debug_variables",
                    event_type="debug_variables",
                    content=json.dumps(saved.all_memory(), ensure_ascii=False),
                    is_terminal=False,
                )
        if message.type == "done":
            committed = store.take_committed_variables()
            if committed is not None:
                yield RunElementSSEMessageDTO(
                    type="debug_variables_committed",
                    event_type="debug_variables_committed",
                    content=committed,
                    is_terminal=False,
                )
        yield message
