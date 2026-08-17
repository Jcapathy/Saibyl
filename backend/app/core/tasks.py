"""Background tasks that survive garbage collection.

`asyncio.create_task` holds no strong reference to the task it returns. Every
API route that fired-and-forgot a worker coroutine — after credits were already
deducted — was betting the event loop would finish the task before the garbage
collector noticed nobody held it (audit item 19). Four routers also carried
their own near-identical `_safe_task` wrapper, which is the two-sources-of-truth
class.

`spawn` is the one way to run a coroutine in the background: it wraps the coro
so a failure is logged instead of lost, and it parks the task in a module-level
set until it completes, which is the strong reference the call sites lacked.
This is not durable jobs — a process restart still loses in-flight work; that
remains the durable-jobs item — but a task can no longer vanish mid-run inside
a healthy process.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

log = structlog.get_logger()

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def spawn(
    coro: Coroutine[Any, Any, Any],
    name: str,
    *,
    on_failure: Callable[[Exception], None] | None = None,
) -> asyncio.Task:
    """Run `coro` in the background, holding a strong reference until it ends.

    `on_failure` runs only when the coroutine raises — after the failure is
    logged — for call sites that must record the failure somewhere a user can
    see it (e.g. marking a simulation failed). A failure inside the handler
    itself is logged rather than swallowed.
    """

    async def _guarded() -> None:
        try:
            await coro
        except Exception as exc:
            log.exception("background_task_failed", task=name)
            if on_failure is not None:
                try:
                    on_failure(exc)
                except Exception:
                    log.exception("background_task_failure_handler_failed", task=name)

    task = asyncio.create_task(_guarded(), name=name)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def pending_count() -> int:
    """How many spawned tasks have not finished. For tests and diagnostics."""
    return len(_BACKGROUND_TASKS)
