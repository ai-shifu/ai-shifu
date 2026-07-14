"""Persistence recorder for the learn /run chain (B6 PR2).

``RunRecorder`` owns every durable write of the /run runtime: progress-record
creation and status/cursor flips, generated-block persistence, and the
post-stream block finalize. Each public method is one transactional *step*
bounded by ``unit_of_work()`` (flaskr/dao/uow.py): the step commits on clean
return and rolls back whole on exception, replacing the historical
flush-then-fail dirty-row behavior where mid-flow ``db.session.flush()`` left
rows in the session that a later commit could persist half-applied.

Step-boundary rules (the Go port contract):

- A step is pure DB work. No recorder method is called while LLM streaming
  or TTS synthesis is in flight; the streaming loop in ``run_inner`` runs
  strictly *between* steps. No ``unit_of_work()`` in this module spans a
  generator ``yield``.
- Rows that must stay invisible until a stream completes (the streamed
  content block, the validation-error block) are *staged* by the caller with
  a plain ``db.session.add()``/``flush()`` — no unit of work — and become
  durable only inside :meth:`finalize_streamed_block` /
  :meth:`save_generated_block` after the stream ends. A client disconnect
  mid-stream therefore still discards the unfinished block via the producer
  rollback in ``runscript_v2.py``, exactly as before PR2.
- A step commit makes *all* session-pending writes durable, including rider
  writes staged by not-yet-migrated collaborators (profile saves, TTS
  sidecar rows, check-text logs). This is why ``retry_on_deadlock`` is NOT
  applied to any step in PR2: a deadlock retry re-runs only the recorder
  method, silently dropping rider writes discarded by the rollback.
  Revisit once PR3 gives the recorder exclusive ownership of /run writes.

Methods take explicit arguments (progress records, generated blocks) — never
a context back-reference — so the persistence surface stays portable.
"""

from flask import Flask

from flaskr.dao import db
from flaskr.dao.uow import unit_of_work
from flaskr.service.learn.models import LearnGeneratedBlock, LearnProgressRecord


class RunRecorder:
    """Transactional persistence steps for the /run runtime."""

    def __init__(self, app: Flask) -> None:
        self.app = app

    def save_new_progress_records(self, records: list[LearnProgressRecord]) -> None:
        """Persist freshly built progress-record placeholder rows as one step.

        The caller builds the rows (NOT_STARTED placeholders for the outline
        parent path, or the gate-interaction attend) without adding them to
        the session; this step owns add + flush + commit.
        """
        if not records:
            return
        with unit_of_work():
            for record in records:
                db.session.add(record)
            db.session.flush()

    def update_progress_pointer(
        self,
        attend: LearnProgressRecord,
        *,
        status: int | None = None,
        block_position: int | None = None,
        outline_item_updated: int | None = None,
    ) -> None:
        """Flip progress status/cursor fields as one step.

        The mutation happens inside the unit of work so a failed step leaves
        the record untouched instead of dirty in the session.
        """
        with unit_of_work():
            if status is not None:
                attend.status = status
            if block_position is not None:
                attend.block_position = block_position
            if outline_item_updated is not None:
                attend.outline_item_updated = outline_item_updated
            db.session.flush()

    def save_generated_block(self, generated_block: LearnGeneratedBlock) -> None:
        """Persist a generated block (new row or accumulated mutations).

        One step for the non-streamed block writes: gate/feedback/interaction
        inserts and the post-LLM interaction-record updates. Never call this
        while a stream for the block is still in flight — stage the row with
        a plain session add instead and finalize after the stream.
        """
        with unit_of_work():
            if not getattr(generated_block, "id", None):
                db.session.add(generated_block)
            db.session.flush()

    def finalize_streamed_block(
        self,
        generated_block: LearnGeneratedBlock,
        generated_content: str,
        attend: LearnProgressRecord,
        *,
        status: int,
        block_position: int,
    ) -> None:
        """Post-stream finalize: block content + progress cursor, atomically.

        Runs after the streaming loop has fully completed (BREAK emitted).
        Committing the content and the cursor advance in one step guarantees
        no reader can observe a streamed block without its position flip or
        vice versa; a failure here rolls both back, leaving the pre-stream
        state for the producer-level rollback/replay path.
        """
        with unit_of_work():
            generated_block.generated_content = generated_content
            if not getattr(generated_block, "id", None):
                db.session.add(generated_block)
            attend.status = status
            attend.block_position = block_position
            db.session.flush()

    def commit_pending_step(self) -> None:
        """Commit writes staged by collaborators the recorder does not own yet.

        Transitional (PR2): the ask path persists its history rows inside
        ``handle_input_ask`` with plain flushes; this step makes them durable
        once the ask stream has fully completed. Tighten by moving those
        writes into explicit recorder methods when the ask flow is
        decomposed.
        """
        with unit_of_work():
            db.session.flush()
