# Copyright (c) 2026 CampusGuard. All rights reserved. Proprietary and confidential; see LICENSE.
"""Check that every name one CampusGuard file takes from another really exists there.

Catches the mistakes imports alone do not: a function renamed in one file but not in the file that
calls it, including imports made lazily inside a function (those only fail when that code runs).
Checks ``from campusguard.x import name`` and ``alias.name`` for modules imported as aliases.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module_files() -> dict[str, Path]:
    found: dict[str, Path] = {"main": ROOT / "main.py"}
    for path in (ROOT / "campusguard").rglob("*.py"):
        parts = list(path.relative_to(ROOT).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        found[".".join(parts)] = path
    return found


def defined_names(tree: ast.Module) -> tuple[set[str], bool]:
    """Top-level names a module defines, and whether it has a dynamic ``__getattr__``."""
    names: set[str] = set()
    dynamic = False

    def collect(statements: list[ast.stmt]) -> None:
        nonlocal dynamic
        for node in statements:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
                dynamic = dynamic or node.name == "__getattr__"
            elif isinstance(node, ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name):
                            names.add(item.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                for block in ("body", "orelse", "finalbody"):
                    collect(getattr(node, block, []))
                for handler in getattr(node, "handlers", []):
                    collect(handler.body)

    collect(tree.body)
    return names, dynamic


def resolve(importer: str, is_package: bool, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    base = importer.split(".")
    if not is_package:
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def check() -> list[str]:
    files = module_files()
    trees = {name: ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for name, path in files.items()}
    exports = {name: defined_names(tree) for name, tree in trees.items()}
    problems: list[str] = []

    def exists(module: str, attribute: str) -> bool:
        if module not in exports:
            return True  # third-party or standard library: not ours to check
        names, dynamic = exports[module]
        return dynamic or attribute in names or f"{module}.{attribute}" in files

    for name, tree in trees.items():
        path = files[name].relative_to(ROOT)
        is_package = files[name].name == "__init__.py"
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = resolve(name, is_package, node)
                if target is None or not (target == "main" or target.split(".")[0] == "campusguard"):
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if not exists(target, alias.name):
                        problems.append(f"{path}:{node.lineno}: '{alias.name}' is not defined in {target}")
                    if f"{target}.{alias.name}" in files:
                        aliases[alias.asname or alias.name] = f"{target}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname and alias.name in files:
                        aliases[alias.asname] = alias.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
                module = aliases[node.value.id]
                if not exists(module, node.attr):
                    problems.append(f"{path}:{node.lineno}: '{node.value.id}.{node.attr}' - {module} has no '{node.attr}'")
    return sorted(set(problems))


def main() -> int:
    problems = check()
    for line in problems:
        print(line)
    print(f"cross-reference check: {len(module_files())} modules, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
