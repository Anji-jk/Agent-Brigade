"""The note of a running agent: written while it runs, gone when it ends, however it ends."""

import pytest

from pipeline.runner.agent_record import read_record, recorded
from pipeline.runner.claude_runner import AgentError, AgentRequest, ClaudeCliRunner
from tests.pipeline.runner.test_stream_events import CWD, INIT, RESULT, SESSION, FakePopen, lines
from tests.pipeline.runner.test_stream_events import FakeProcess as Process


def test_the_note_exists_only_while_the_block_runs(tmp_path):
    path = tmp_path / "control" / "SMT-62.agent"
    with recorded(path, 99, "abc"):
        found = read_record(path)
        assert (found.pid, found.session_id) == (99, "abc") and found.started_at
    assert not path.exists()


def test_the_note_goes_even_when_the_block_fails(tmp_path):
    path = tmp_path / "SMT-62.agent"
    with pytest.raises(RuntimeError), recorded(path, 99, "abc"):
        raise RuntimeError("boom")
    assert not path.exists()


def test_without_a_path_nothing_is_written(tmp_path):
    with recorded(None, 99, "abc"):
        pass
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"pid": true, "session_id": "x"}',
                                  '{"pid": 5}', '{"pid": "5", "session_id": "x"}'])  # fmt: skip
def test_a_damaged_or_foreign_note_reads_as_none(tmp_path, text):
    path = tmp_path / "x.agent"
    path.write_text(text, encoding="utf-8")
    assert read_record(path) is None
    assert read_record(tmp_path / "missing.agent") is None


def _request(tmp_path, record):
    return AgentRequest(
        agent="builder", prompt="Do it", cwd=CWD, session_id=SESSION, resume=False,
        events_file=tmp_path / "builder.events.jsonl", timeout=30, record_file=record,
    )  # fmt: skip


def test_the_runner_notes_its_agent_while_it_waits_and_clears_the_note(tmp_path):
    record, seen = tmp_path / "SMT-62.agent", []

    class Watching(Process):
        def wait(self, timeout=None):
            seen.append(read_record(record))
            return super().wait(timeout)

    popen = FakePopen(Watching(lines(INIT, RESULT)))
    ClaudeCliRunner("claude", popen=popen, kill=popen.kill).run(_request(tmp_path, record))
    assert [(r.pid, r.session_id) for r in seen] == [(4242, SESSION)]
    assert not record.exists()


def test_the_note_is_cleared_when_the_agent_is_killed_for_taking_too_long(tmp_path):
    record = tmp_path / "SMT-62.agent"
    popen = FakePopen(Process(lines(INIT), hang=True))
    runner = ClaudeCliRunner("claude", popen=popen, kill=popen.kill)
    with pytest.raises(AgentError):
        runner.run(_request(tmp_path, record))
    assert popen.killed and not record.exists()
