"""A loop that died leaves tasks half-done and maybe an agent: both are found, by command line."""

from core.db import get_session
from core.db.repositories import merge_rows
from core.runs import run_directory
from pipeline.control import interrupted as it
from pipeline.control import task_control as tc
from pipeline.control.launch import Launch, write_launch
from pipeline.runner.agent_record import recorded
from pipeline.stages import checkpoint
from pipeline.stages.builder_run import build_attempt
from tests.pipeline.stages.stage_setup import RUN
from tests.pipeline.stages.team_setup import TeamRunner, team_project

KEY = "SMT-62"
SESSION = "11111111-2222-3333-4444-555555555555"
LOOP = f"python -m pipeline.stages loop {RUN}"


def newest(engine):
    with get_session(engine) as session:
        found = merge_rows.newest_attempt(session, RUN, KEY)
        assert found is not None
        sub, attempt = found
        return sub.status, attempt.outcome


def word_of(folder):
    """The task's settled word; it must exist."""
    word = tc.settled(folder, KEY)
    assert word is not None
    return word


def died_in_the_middle(tmp_path, *, stages=("builder",)):
    """A task built once, whose loop then died: launch.json names a process that is gone."""
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    for stage in stages:
        checkpoint.save(repo, RUN, KEY, 1, stage)
    folder = run_directory(repo, RUN)
    write_launch(folder, Launch(4000, ["python", "-m", "pipeline.stages", "loop", RUN], "then"))
    return repo, engine, folder


def test_an_unfinished_task_of_a_dead_loop_becomes_stopped_at_its_checkpoint(tmp_path):
    repo, engine, folder = died_in_the_middle(tmp_path, stages=("builder", "checks"))
    assert newest(engine) == ("running", "built")
    found = it.notice(engine, repo, RUN, lambda pid: None)
    assert found == [KEY]
    assert newest(engine) == ("stopped", "stopped")
    word = word_of(folder)
    assert (word.state, word.stage, word.attempt) == (tc.STOPPED, "tester", 1)


def test_nothing_is_touched_while_a_loop_of_the_run_is_running(tmp_path):
    repo, engine, _ = died_in_the_middle(tmp_path)
    assert it.notice(engine, repo, RUN, lambda pid: LOOP if pid == 4000 else None) == []
    assert newest(engine) == ("running", "built")


def test_a_run_that_never_started_has_nothing_interrupted(tmp_path):
    repo, config, engine = team_project(tmp_path)
    build_attempt(config, RUN, KEY, TeamRunner(), 1, engine)
    assert it.notice(engine, repo, RUN, lambda pid: None) == []  # no launch.json: not started


def test_noticing_twice_changes_nothing_the_second_time(tmp_path):
    repo, engine, folder = died_in_the_middle(tmp_path)
    assert it.notice(engine, repo, RUN, lambda pid: None) == [KEY]
    first = tc.settled(folder, KEY)
    assert it.notice(engine, repo, RUN, lambda pid: None) == []
    assert tc.settled(folder, KEY) == first


def test_a_cancelled_task_stays_cancelled(tmp_path):
    repo, engine, folder = died_in_the_middle(tmp_path)
    tc.settle(folder, KEY, tc.CANCELLED, "builder", 1)
    assert it.notice(engine, repo, RUN, lambda pid: None) == []
    assert word_of(folder).state == tc.CANCELLED


def test_a_request_that_was_waiting_when_the_loop_died_is_kept_as_asked(tmp_path):
    repo, engine, folder = died_in_the_middle(tmp_path)
    tc.ask(folder, KEY, tc.CANCEL)
    it.notice(engine, repo, RUN, lambda pid: None)
    assert word_of(folder).state == tc.CANCELLED
    assert tc.pending(folder, KEY) is None


def test_the_orphan_agent_is_stopped_only_when_its_session_is_in_the_command_line(tmp_path):
    folder, killed = tmp_path, []
    path = tc.agent_record_path(folder, KEY)
    with recorded(path, 777, SESSION):
        ours = f"claude -p --session-id {SESSION}"
        assert it.reap_orphan(folder, KEY, lambda pid: ours, killed.append) is True
    assert [k.pid for k in killed] == [777]
    assert not path.exists()  # the note is spent


def test_a_process_that_took_the_id_over_is_left_alone(tmp_path):
    folder, killed = tmp_path, []
    path = tc.agent_record_path(folder, KEY)
    stranger = "notepad.exe C:/notes.txt"
    with recorded(path, 777, SESSION):
        assert it.reap_orphan(folder, KEY, lambda pid: stranger, killed.append) is False
        path_now = path.exists()
    assert killed == [] and path_now is False  # not killed; the stale note was dropped


def test_an_agent_that_is_gone_is_not_killed_and_no_note_means_nothing_to_do(tmp_path):
    killed = []
    assert it.reap_orphan(tmp_path, KEY, lambda pid: None, killed.append) is False
    with recorded(tc.agent_record_path(tmp_path, KEY), 777, SESSION):
        assert it.reap_orphan(tmp_path, KEY, lambda pid: None, killed.append) is False
    assert killed == []


def test_noticing_stops_the_orphan_before_the_task_is_marked(tmp_path):
    repo, engine, folder = died_in_the_middle(tmp_path)
    killed = []
    with recorded(tc.agent_record_path(folder, KEY), 777, SESSION):
        it.notice(engine, repo, RUN, lambda pid: f"claude --resume {SESSION}", killed.append)
    assert [k.pid for k in killed] == [777]
    assert word_of(folder).state == tc.STOPPED


def test_a_lock_left_by_a_killed_loop_is_removed(tmp_path):
    (tmp_path / "story.lock").write_text("23644", encoding="utf-8")
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: None) is True  # no such process
    assert not (tmp_path / "story.lock").exists()


def test_a_lock_whose_id_now_belongs_to_another_program_is_stale_too(tmp_path):
    (tmp_path / "story.lock").write_text("23644", encoding="utf-8")
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: "chrome.exe --type=gpu") is True


def test_a_lock_held_by_a_running_loop_of_the_run_is_kept(tmp_path):
    (tmp_path / "story.lock").write_text("23644", encoding="utf-8")
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: LOOP) is False
    assert (tmp_path / "story.lock").exists()


def test_the_loop_of_another_run_does_not_hold_this_runs_lock(tmp_path):
    (tmp_path / "story.lock").write_text("23644", encoding="utf-8")
    other = "python -m pipeline.stages loop SMT-99-20261113-aaaa"
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: other) is True


def test_no_lock_or_a_damaged_one_is_not_an_error(tmp_path):
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: None) is False
    (tmp_path / "story.lock").write_text("not a number", encoding="utf-8")
    assert it.clear_stale_lock(tmp_path, RUN, lambda pid: None) is True
