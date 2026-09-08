"""Lightweight background task runner (spec §52).

Uses a process-local thread pool so PDF processing never blocks the request/response
cycle. The call signature (`submit(app, fn, *args, **kwargs)`) is deliberately the only
thing pipeline code depends on, so this module can be swapped for a Celery+Redis backed
task queue in production without touching `app/ingestion/pipeline.py` or its callers.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("rse_intelligence.tasks")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rse-worker")


def submit(app, fn, *args, **kwargs):
    def _run():
        with app.app_context():
            try:
                fn(*args, **kwargs)
            except Exception:
                logger.exception("Background task %s failed", getattr(fn, "__name__", fn))

    if app.config.get("TESTING"):
        # Run inline: the test process/DB/upload folder can be torn down before a real
        # background thread finishes, which would race with test fixture cleanup.
        _run()
        return None

    return _executor.submit(_run)


def run_synchronously(app, fn, *args, **kwargs):
    """Used by tests/CLI to execute a task inline and wait for the result."""
    with app.app_context():
        return fn(*args, **kwargs)
