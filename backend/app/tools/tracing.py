"""Recording an explicit tool invocation onto the project blackboard.

`tool_run` is the one way a handler calls a registered tool. It writes a
`ToolInvocation` (running → ok/error, with a real duration), emits a live
``tool`` event so the activity feed shows "Calling {tool}" while the run is in
flight, and caps the list the same way `Engine.emit` caps events.

Every tracing parameter downstream is optional: with no engine/state the tool
still runs, just untraced — so secondary call paths (a re-derived scorecard, a
setup-only pass) don't manufacture phantom invocations.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

from app.domain.models import ToolInvocation
from app.tools.registry import get

MAX_INVOCATIONS = 400


class _Handle:
    """Handed to the caller so it can attach a result summary to the record."""

    def __init__(self, record: ToolInvocation) -> None:
        self.record = record

    def result(self, summary: str) -> None:
        self.record.result_summary = summary[:300]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def tool_run(eng, st, task_id: str, tool_id: str, args_summary: str = "") -> Iterator[_Handle]:
    """Record one invocation of `tool_id` around the enclosed call."""
    spec = get(tool_id).spec
    record = ToolInvocation(
        id=f"tv-{len(st.tool_invocations) + 1}-{tool_id}-{st.tick}",
        toolId=spec.id, toolName=spec.name, category=spec.category, taskId=task_id,
        argsSummary=args_summary[:300], status="running",
        startedTick=st.tick, startedAt=_now(),
    )
    st.tool_invocations.insert(0, record)
    del st.tool_invocations[MAX_INVOCATIONS:]
    if eng is not None:
        eng.emit(st, "data", "tool", f"Calling {spec.name} — {args_summary}"[:160], task_id)
    started = time.perf_counter()
    try:
        yield _Handle(record)
    except Exception as e:  # noqa: BLE001 — the failure belongs in the trace
        record.status = "error"
        record.error = f"{e}"[:300]
        raise
    else:
        record.status = "ok"
    finally:
        record.duration_ms = round((time.perf_counter() - started) * 1000, 1)
        record.finished_at = _now()


def traced(eng, st, task_id: Optional[str], tool_id: str, args_summary: str,
           fn: Callable[..., Any], /, *args,
           summarize: Optional[Callable[[Any], str]] = None,
           **kwargs) -> Any:
    """Run one tool call, traced when an engine/state/task is supplied.

    `fn` is passed explicitly (rather than looked up) so the call site reads as
    the computation it is; pass ``get(tool_id).run`` to go through the registry.

    The tracing parameters are **positional-only** so they cannot collide with
    the tool's own keyword arguments: ``run_mmm`` takes an ``st=`` of its own
    (the project, for per-indicator aggregation), and without the ``/`` that
    silently bound to this function's ``st`` instead — every traced OLS fit then
    failed with "multiple values for argument 'st'".
    """
    if eng is None or st is None or not task_id:
        return fn(*args, **kwargs)
    with tool_run(eng, st, task_id, tool_id, args_summary) as h:
        out = fn(*args, **kwargs)
        if summarize is not None:
            h.result(summarize(out))
        return out
