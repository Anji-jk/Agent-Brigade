from pipeline.feed.readers import json_lines, read_lines


def test_a_missing_file_has_no_lines(tmp_path):
    assert read_lines(tmp_path / "none.jsonl") == []
    assert json_lines(tmp_path / "none.jsonl") == []


def test_lines_keep_their_line_numbers_when_one_is_bad(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text('{"a": 1}\nnot json\n[1, 2]\n{"b": 2}\n{"torn": ', encoding="utf-8")
    assert json_lines(path) == [(0, {"a": 1}), (3, {"b": 2})]


def test_undecodable_bytes_do_not_stop_reading(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_bytes(b'{"a": "\xff"}\n')
    assert len(json_lines(path)) == 1
