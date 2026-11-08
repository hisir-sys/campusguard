"""Whole-app search: pages, settings and actions that the nav search box can run.

Pure Python (no Qt), so ranking is easy to test. The main window builds the
list of commands; the sidebar only ranks and runs them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Command:
    title: str
    group: str                         # "Page", "Setting" or "Action"
    run: Callable[[], None]
    keywords: tuple[str, ...] = field(default_factory=tuple)


def _score(command: Command, needle: str) -> int:
    """Higher is better; 0 means no match."""
    title = command.title.casefold()
    if title == needle:
        return 100
    if title.startswith(needle):
        return 80
    if any(word.startswith(needle) for word in title.split()):
        return 60
    if needle in title:
        return 40
    for keyword in command.keywords:
        keyword = keyword.casefold()
        if keyword == needle or keyword.startswith(needle):
            return 30
        if needle in keyword:
            return 20
    return 0


def search_commands(commands: list[Command], query: str, limit: int = 8) -> list[Command]:
    needle = " ".join(query.casefold().split())
    if not needle:
        return []
    ranked = [(score, index, command) for index, command in enumerate(commands) if (score := _score(command, needle))]
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [command for _score_value, _index, command in ranked[:limit]]
