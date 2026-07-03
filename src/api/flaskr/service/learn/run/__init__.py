"""Run-chain collaborators extracted from ``RunScriptContextV2``.

This package hosts the incremental decomposition of the learn /run SSE
runtime (ExecPlan: ``docs/exec-plans/active/learn-run-decomposition.md``):

- PR1: ``emitter.py`` — SSE event construction and yield-sequencing.
- PR2: ``recorder.py`` — persistence with per-step unit_of_work.
- PR3: ``state.py`` — pure outline/progress reads (planned).

The SSE event names and payload shapes are FROZEN (see ``learn/AGENTS.md``);
the golden suite under ``tests/golden/`` is the contract gate.
"""

from flaskr.service.learn.run.emitter import RunEventEmitter
from flaskr.service.learn.run.recorder import RunRecorder

__all__ = ["RunEventEmitter", "RunRecorder"]
