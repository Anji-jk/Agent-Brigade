import json

import pytest

from core.files import atomic
from core.files.atomic import write_json_atomic


def test_writes_json_and_creates_the_folder(tmp_path):
    path = tmp_path / "a" / "b" / "plan.json"
    write_json_atomic(path, {"name": "Skill Matrix ✓", "n": [1, 2]})
    assert json.loads(path.read_text(encoding="utf-8")) == {"name": "Skill Matrix ✓", "n": [1, 2]}
    assert path.read_text(encoding="utf-8").endswith("}\n")


def test_replaces_an_existing_file(tmp_path):
    path = tmp_path / "plan.json"
    write_json_atomic(path, {"v": 1})
    write_json_atomic(path, {"v": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["plan.json"]


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temporary(tmp_path):
    path = tmp_path / "plan.json"
    write_json_atomic(path, {"v": 1})
    with pytest.raises(TypeError):
        write_json_atomic(path, {"v": object()})  # not JSON
    assert json.loads(path.read_text(encoding="utf-8")) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["plan.json"]


def test_a_failed_replace_leaves_no_temporary(tmp_path, monkeypatch):
    def refuse(*_):
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        write_json_atomic(tmp_path / "plan.json", {"v": 1})
    assert list(tmp_path.iterdir()) == []
