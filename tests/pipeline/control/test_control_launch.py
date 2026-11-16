import json
import sys
import time

import pytest

from pipeline.control import launch as lc
from pipeline.control.processes import command_line

RUN = "SMT-61-20261113-6b1a"


def lines(**by_pid):
    """A fake `command_line`: {pid: line}; any other pid is not running."""
    return lambda pid: by_pid.get(f"p{pid}")


def test_a_launch_record_is_read_back(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(4242, ["python", "-m", "pipeline.stages"], "2026-11-16"))
    found = lc.read_launch(tmp_path)
    assert found == lc.Launch(4242, ["python", "-m", "pipeline.stages"], "2026-11-16")


def test_a_run_never_launched_has_no_record(tmp_path):
    assert lc.read_launch(tmp_path) is None


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"pid": "x"}', '{"pid": true}'])
def test_a_damaged_record_reads_as_none(tmp_path, text):
    (tmp_path / lc.LAUNCH_FILE).write_text(text, encoding="utf-8")
    assert lc.read_launch(tmp_path) is None


def test_the_loop_command_names_the_run_and_the_module():
    assert lc.loop_command(RUN, "py") == ["py", "-m", "pipeline.stages", "loop", RUN]


@pytest.mark.parametrize(
    "line",
    [
        f"python -m pipeline.stages loop {RUN}",
        f'"C:\\x\\python.exe" -m pipeline.stages loop {RUN}',
        f"python -m pipeline.stages story {RUN}",  # one started by hand in a terminal
    ],
)
def test_a_process_with_the_loops_command_line_is_ours(line):
    assert lc.is_loop_process(line, RUN)


@pytest.mark.parametrize(
    "line",
    [
        None,
        "notepad.exe",
        f"python -m pipeline.stages loop {RUN}-2",  # another run whose id starts the same way
        "python -m pipeline.stages loop SMT-99-20261113-aaaa",
        f"python -m pipeline.stages build {RUN} SMT-62",  # a stage, not the loop
    ],
)
def test_any_other_command_line_is_not_ours(line):
    assert not lc.is_loop_process(line, RUN)


def test_the_loop_is_alive_while_its_recorded_process_still_runs_our_command(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    ours = f"python -m pipeline.stages loop {RUN}"
    assert lc.loop_alive(tmp_path, RUN, lines(p7=ours))


def test_a_reused_process_id_does_not_count_as_the_loop(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(7, [], "t"))
    assert not lc.loop_alive(tmp_path, RUN, lines(p7="notepad.exe"))


def test_a_loop_started_by_hand_is_found_by_its_lock_file(tmp_path):
    (tmp_path / "story.lock").write_text("9", encoding="utf-8")
    ours = f"python -m pipeline.stages story {RUN}"
    assert lc.loop_alive(tmp_path, RUN, lines(p9=ours))


def test_nothing_recorded_and_no_lock_means_not_alive(tmp_path):
    assert not lc.loop_alive(tmp_path, RUN, lines())


def test_launching_records_the_process_and_runs_it_from_the_repository_folder(tmp_path):
    seen = {}

    class Fake:
        pid = 4242

    def popen(command, **kwargs):
        seen.update(command=command, **kwargs)
        return Fake()

    run_dir, repo = tmp_path / "run", tmp_path / "repo"
    repo.mkdir()
    launch = lc.launch_loop(run_dir, RUN, repo, python="py", popen=popen)
    assert launch.pid == 4242 and launch.command == ["py", "-m", "pipeline.stages", "loop", RUN]
    assert seen["command"] == launch.command and seen["cwd"] == repo
    assert lc.read_launch(run_dir) == launch
    assert (run_dir / lc.LOG_FILE).exists()  # the loop's output has somewhere to go


def test_a_detached_process_outlives_its_caller_and_can_be_found(tmp_path):
    child = lc.spawn_detached(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, tmp_path / "out.log"
    )
    try:
        for _ in range(100):  # a new process shows its command only once it has started
            if "time.sleep" in (command_line(child.pid) or ""):
                break
            time.sleep(0.05)
        assert "time.sleep" in (command_line(child.pid) or "")
    finally:
        child.kill()
        child.wait()


def test_the_record_file_is_plain_json_a_person_can_read(tmp_path):
    lc.write_launch(tmp_path, lc.Launch(1, ["a"], "t"))
    assert json.loads((tmp_path / lc.LAUNCH_FILE).read_text(encoding="utf-8"))["pid"] == 1
