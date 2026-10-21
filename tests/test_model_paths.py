from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

from campusguard.model_paths import with_aliases


def test_alias_candidates():
    assert with_aliases(Path("models/model_16_m3_0.8888.pth")) == [
        Path("models/model_16_m3_0.8888.pth"),
        Path("models/fight_mc3_18.pth"),
    ]
    assert with_aliases(Path("models/fight_mc3_18.pth")) == [Path("models/fight_mc3_18.pth")]
    assert with_aliases(Path("models/yolo11n.pt")) == [Path("models/yolo11n.pt")]


def _resolver(tmp_path):
    # ai_pipeline needs torch/cv2 at import time; the resolver itself does not.
    stubs = {name: mock.MagicMock() for name in ("torch", "torch.nn", "cv2", "numpy", "ultralytics")}
    with mock.patch.dict(sys.modules, stubs):
        sys.modules.pop("campusguard.ai_pipeline", None)
        sys.modules.pop("campusguard.model_registry", None)
        import campusguard.ai_pipeline as pipeline

        return pipeline


def test_missing_duplicate_falls_back_to_shipped_copy(tmp_path, monkeypatch):
    from campusguard import model_paths

    # A made-up alias, so a dev checkout that really has both files cannot mask the logic.
    monkeypatch.setitem(model_paths.DUPLICATE_MODEL_ALIASES, "copy_only_in_name.pth", "fight_mc3_18.pth")
    pipeline = _resolver(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "fight_mc3_18.pth").write_bytes(b"x")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    resolved = pipeline.resolve_model_path("models/copy_only_in_name.pth")
    assert resolved == tmp_path / "models" / "fight_mc3_18.pth"


def test_existing_file_is_never_replaced_by_alias(tmp_path, monkeypatch):
    from campusguard import model_paths

    monkeypatch.setitem(model_paths.DUPLICATE_MODEL_ALIASES, "copy_only_in_name.pth", "fight_mc3_18.pth")
    pipeline = _resolver(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "fight_mc3_18.pth").write_bytes(b"a")
    (tmp_path / "models" / "copy_only_in_name.pth").write_bytes(b"b")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    resolved = pipeline.resolve_model_path("models/copy_only_in_name.pth")
    assert resolved == tmp_path / "models" / "copy_only_in_name.pth"


def test_unknown_missing_file_is_returned_unchanged(tmp_path, monkeypatch):
    pipeline = _resolver(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert pipeline.resolve_model_path("models/nope.pt") == Path("models/nope.pt")
