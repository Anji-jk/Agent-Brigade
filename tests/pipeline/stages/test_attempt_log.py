import json

from pipeline.stages import attempt_log as a
from pipeline.stages import story_loop as s
from pipeline.stages.task_run import run_task
from tests.pipeline.stages.stage_setup import FAIL, RUN
from tests.pipeline.stages.team_setup import TeamRunner, answer_of_reviewer, team_project
from tests.pipeline.stages.test_story_loop import StoryRunner, project


def steps(repo, key="SMT-62", number=1):
    path = a.attempt_dir(repo, RUN, key, number) / "events.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_an_attempt_keeps_its_files_in_one_folder(tmp_path):
    folder = a.attempt_dir(tmp_path, RUN, "SMT-62", 2)
    assert folder == tmp_path / ".agent-brigade" / "runs" / RUN / "attempts" / "SMT-62-2"
    assert a.agent_events_path(tmp_path, RUN, "SMT-62", 2, "tester") == (
        folder / "tester.events.jsonl"
    )


def test_a_step_is_one_json_line_with_the_time_and_its_facts(tmp_path):
    log = a.AttemptLog(tmp_path, RUN, "SMT-62", 1)
    assert log.emit("builder_started", model="sonnet") and log.emit("builder_finished", ok=True)
    found = steps(tmp_path)
    assert [x["step"] for x in found] == ["builder_started", "builder_finished"]
    assert found[0]["model"] == "sonnet" and found[0]["at"].endswith("+00:00")


def test_a_log_that_cannot_be_written_never_stops_the_task(tmp_path):
    blocked = tmp_path / ".agent-brigade"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    assert a.AttemptLog(tmp_path, RUN, "SMT-62", 1).emit("builder_started") is False


def test_a_task_logs_each_stage_and_hands_each_agent_its_event_file(tmp_path):
    repo, config, engine = team_project(tmp_path)
    runner = TeamRunner()
    assert run_task(config, RUN, "SMT-62", runner, engine=engine).ok
    assert [x["step"] for x in steps(repo)] == [
        "attempt_started", "worktree_ready", "builder_started", "builder_finished",
        "checks_finished", "tester_started", "tester_finished", "judge_started",
        "judge_finished",
    ]  # fmt: skip
    for role in ("builder", "tester", "reviewer"):
        asked = runner.of(role)[0]
        assert asked.events_file == a.agent_events_path(repo, RUN, "SMT-62", 1, role)


def test_the_steps_say_what_happened(tmp_path):
    repo, config, engine = team_project(tmp_path)
    run_task(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    by = {x["step"]: x for x in steps(repo)}
    assert by["builder_finished"]["ok"] is True and by["builder_finished"]["changed"] == 1
    assert by["checks_finished"]["passed"] is True
    assert by["judge_finished"]["outcome"] == "done" and by["judge_finished"]["commit"]


def test_a_failed_attempt_says_why_in_its_log(tmp_path):
    repo, config, engine = team_project(tmp_path, verify=(FAIL,))
    run_task(config, RUN, "SMT-62", TeamRunner(), engine=engine)
    last = steps(repo)[-1]
    assert last["step"] == "judge_finished" and last["outcome"] == "failed" and last["reasons"]


def test_the_story_loop_logs_the_merge_and_each_retry_in_its_attempt_folder(tmp_path):
    repo, config, engine = project(tmp_path)
    runner = StoryRunner(reviewer_text=[answer_of_reviewer(met=(False,)), answer_of_reviewer()])
    assert s.run_story(config, RUN, runner, engine=engine).ok
    assert "merge_finished" not in [x["step"] for x in steps(repo, number=1)]  # it failed
    second = steps(repo, number=2)
    assert [x["step"] for x in second][-2:] == ["merge_started", "merge_finished"]
    assert second[-1]["merged"] is True and second[-1]["how"] == "fast-forward"
