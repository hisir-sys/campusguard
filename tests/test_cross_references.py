"""Every name one file takes from another exists, and the checker really catches mistakes."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_cross_references", ROOT / "scripts" / "check_cross_references.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_file_uses_a_name_another_file_does_not_define():
    assert _load_checker().check() == []


def test_checker_catches_renamed_functions_even_in_lazy_imports(tmp_path, monkeypatch):
    package = tmp_path / "campusguard"
    package.mkdir()
    (tmp_path / "main.py").write_text("from campusguard.a import real\n")
    (package / "__init__.py").write_text("")
    (package / "a.py").write_text("def real():\n    return 1\n\nVALUE = 2\n")
    (package / "b.py").write_text(
        "from campusguard import a\n"
        "from campusguard.a import real, renamed_away\n"
        "from .a import also_missing\n"
        "def later():\n"
        "    from campusguard.a import lazily_missing\n"
        "    return a.real() + a.VALUE + a.typo\n"
    )
    checker = _load_checker()
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    problems = " | ".join(checker.check())
    for missing in ("renamed_away", "also_missing", "lazily_missing", "a.typo"):
        assert missing in problems, problems
    assert "'real'" not in problems and "a.VALUE" not in problems and "a.real" not in problems
