"""Ensure every task function passed to enqueue_task has the @rq.job decorator.

enqueue_task() relies on task_func.helper (set by Flask-RQ2's @rq.job).
Missing the decorator causes "'function' object has no attribute 'helper'"
at runtime. This test catches that regression statically.
"""
import inspect

import pytest

from ui import tasks


# Collect all public task functions defined in ui/tasks.py
# (exclude helpers like enqueue_task, with_app_context, failure handlers)
TASK_FUNCTIONS = [
    obj for name, obj in inspect.getmembers(tasks)
    if callable(obj)
    and getattr(obj, '__module__', None) == 'ui.tasks'
    and not name.startswith('_')
    and name not in ('enqueue_task', 'with_app_context',
                     'host_job_failure_handler', 'instance_job_failure_handler')
]


@pytest.mark.parametrize("task_func", TASK_FUNCTIONS, ids=lambda f: f.__name__)
def test_task_has_rq_job_decorator(task_func):
    """Every task function must have the .helper attribute from @rq.job."""
    assert hasattr(task_func, 'helper'), (
        f"{task_func.__name__} is missing the @rq.job decorator. "
        f"enqueue_task() requires task_func.helper which is set by @rq.job."
    )
