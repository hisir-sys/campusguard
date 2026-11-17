"""One combined notice for camera problems.

A camera that cannot connect retries every few seconds, and a school may have dozens of them. Showing a
popup per camera per retry buries the screen, so the window keeps a set of cameras that currently have a
problem and shows a single, updating message about all of them.
"""
from __future__ import annotations

# Shown by a camera thread when the operator stops it on purpose; that is not a problem to report.
OPERATOR_STOP_MESSAGE = "Camera stopped by operator."

PROBLEM_STATUSES = frozenset({"OFFLINE", "ERROR"})
NAMES_SHOWN = 3


def is_problem(status: str, message: str) -> bool:
    """True when a status report means the camera needs attention (and the operator did not cause it)."""
    return status in PROBLEM_STATUSES and bool(message) and message != OPERATOR_STOP_MESSAGE


def describe_problems(problems: list[tuple[str, str]]) -> str:
    """Words for the notice. `problems` is [(camera name, message)] for every camera that has one."""
    if not problems:
        return ""
    if len(problems) == 1:
        name, message = problems[0]
        return f"{name}: {message}"
    names = [name for name, _ in problems]
    shown = ", ".join(names[:NAMES_SHOWN])
    extra = len(names) - NAMES_SHOWN
    if extra > 0:
        shown += f" and {extra} more"
    return f"{len(names)} cameras need attention: {shown}. Check their addresses and credentials in Cameras."
