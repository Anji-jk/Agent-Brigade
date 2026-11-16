import json
import threading
import time

from core.files.atomic import write_json_atomic
from pipeline.planning.plan_file import load_plan, plan_path
from pipeline.runner.claude_runner import AgentReply
from pipeline.stages import events
from pipeline.stages import story_loop as s
from pipeline.stages.story_report import BLOCKED, FAILED, MERGED, NEEDS_PERSON
from tests.pipeline.stages.stage_setup import FAIL, OK, RUN
from tests.pipeline.stages.team_setup import (
    BUILDER_REPORT,
    NEW_TEST,
    TeamRunner,
    answer_of_reviewer,
    answer_of_tester,
    team_project,
)
from tests.pipeline.workspace.repo import git

MORE = "\ndef test_more():\n    assert 3 == 3\n"


class StoryRunner(TeamRunner):
    """The Team fake, where the second task builds src/b.py and adds a test of its own."""

    def run(self, request):
        if "SMT-63" in str(request.cwd):
            self.writes["builder"] = {"src/b.py": "y = 2\n"}
            self.writes["tester"] = {"tests/test_new.py": NEW_TEST + MORE}
        return super().run(request)


class HoldingRunner:
    """A fake Claude that holds each Builder for a moment and counts how many are in at once.

    Safe to share between threads (the Team fake is not): it keeps no state a request changes.
    """

    def __init__(self, hold=0.5):
        self.hold, self.active, self.peak = hold, 0, 0
        self.lock = threading.Lock()
        self.requests = []

    def run(self, request):
        name = "b" if "SMT-63" in str(request.cwd) else "a"
        with self.lock:
            self.requests.append(request)
        text = answer_of_reviewer()
        if request.agent == "builder":
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(self.hold)
            (request.cwd / "src").mkdir(exist_ok=True)
            (request.cwd / "src" / f"{name}.py").write_text(f"{name} = 1\n", encoding="utf-8")
            with self.lock:
                self.active -= 1
            text = BUILDER_REPORT
        elif request.agent == "tester":
            (request.cwd / "tests").mkdir(exist_ok=True)
            (request.cwd / "tests" / f"test_{name}.py").write_text(NEW_TEST, encoding="utf-8")
            text = answer_of_tester(coverage={1: [f"tests/test_{name}.py::test_new"]})
        return AgentReply(
            text, request.session_id, cost_usd=0.1, turns=3, duration_ms=2000,
            input_tokens=10, output_tokens=5, cache_tokens=1, model_used="claude-sonnet",
        )  # fmt: skip


def project(tmp_path, *, depends=True, first_verify=(OK,), max_retries=2, together=False,
            max_parallel=3):  # fmt: skip
    repo, config, engine = team_project(tmp_path, verify=first_verify)
    plan = load_plan(repo, RUN)
    second = plan["tasks"][1]
    second.update(files=["src/b.py"], verification=[OK], acceptance_criteria=["It works."])
    if not depends or together:
        second["depends_on"] = []
    for one in plan["tasks"]:
        one["parallel_safe"] = together  # files differ, so the plan could confirm it
    write_json_atomic(plan_path(repo, RUN), plan)
    limits = {"max_retries": max_retries, "max_parallel": max_parallel}
    return repo, config.model_copy(update=limits), engine


def story_files(tmp_path):
    root = tmp_path / "bw" / RUN / "story"
    return {p.name for p in (root / "src").glob("*.py")}


def kinds(repo, key=None):
    return [x["kind"] for x in events.read_events(repo, RUN) if key in (None, x.get("key"))]


def test_every_task_is_built_and_merged_in_dependency_order(tmp_path):
    repo, config, engine = project(tmp_path)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine)
    assert result.ok and result.statuses() == {"SMT-62": MERGED, "SMT-63": MERGED}
    assert story_files(tmp_path) == {"a.py", "b.py"}
    merged = [x["key"] for x in events.read_events(repo, RUN) if x["kind"] == "task_merged"]
    assert merged == ["SMT-62", "SMT-63"]
    assert git(repo, "status", "--porcelain") == ""


def test_running_the_loop_again_does_nothing_and_spends_nothing(tmp_path):
    repo, config, engine = project(tmp_path)
    s.run_story(config, RUN, StoryRunner(), engine=engine)
    again = StoryRunner()
    result = s.run_story(config, RUN, again, engine=engine)
    assert result.ok and again.requests == []
    assert result.tasks["SMT-62"].detail == "already merged"
    assert kinds(repo).count("task_merged") == 2  # not recorded a second time


def test_a_failed_attempt_is_retried_and_then_merged(tmp_path):
    repo, config, engine = project(tmp_path)
    runner = StoryRunner(reviewer_text=[answer_of_reviewer(met=(False,)), answer_of_reviewer()])
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.ok and result.tasks["SMT-62"].attempts == 2
    assert kinds(repo, "SMT-62") == [
        "task_started", "task_failed", "task_started", "task_done", "task_merged",
    ]  # fmt: skip
    assert len(runner.of("builder")) == 3  # two for SMT-62, one for SMT-63


def test_a_task_failed_for_good_blocks_its_dependents(tmp_path):
    repo, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=1)
    runner = StoryRunner()
    result = s.run_story(config, RUN, runner, engine=engine)
    assert not result.ok
    assert result.statuses() == {"SMT-62": FAILED, "SMT-63": BLOCKED}
    assert result.tasks["SMT-62"].attempts == 2
    assert "SMT-62" in result.tasks["SMT-63"].detail
    assert not any("SMT-63" in str(r.cwd) for r in runner.requests)  # nothing spent on it
    assert "story_stopped" in kinds(repo)


def test_an_independent_task_continues_when_another_failed_for_good(tmp_path):
    repo, config, engine = project(tmp_path, depends=False, first_verify=(FAIL,), max_retries=0)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine)
    assert result.statuses() == {"SMT-62": FAILED, "SMT-63": MERGED}
    assert story_files(tmp_path) == {"b.py"}


def test_an_attempt_that_needs_a_person_stops_that_task_with_no_retry(tmp_path):
    repo, config, engine = project(tmp_path, depends=False)
    runner = StoryRunner(reviewer={"src/a.py": "x = 99\n"})  # a Reviewer that edits files
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.tasks["SMT-62"].status == NEEDS_PERSON
    assert result.tasks["SMT-62"].attempts == 1 and len(runner.of("builder")) == 2
    assert not result.ok


def test_the_summary_names_every_task_and_the_next_step(tmp_path):
    repo, config, engine = project(tmp_path, first_verify=(FAIL,), max_retries=0)
    result = s.run_story(config, RUN, StoryRunner(), engine=engine)
    text = result.text()
    assert "SMT-62" in text and "Failed" in text and "SMT-63" in text and "Blocked" in text
    saved = json.loads((repo / ".agent-brigade" / "runs" / RUN / "story-report.json").read_text())
    assert saved["ok"] is False and saved["tasks"]["SMT-63"]["status"] == BLOCKED


def test_independent_tasks_that_are_parallel_safe_run_at_the_same_time(tmp_path):
    repo, config, engine = project(tmp_path, together=True)
    runner = HoldingRunner(hold=2.0)  # long enough that a slow worktree setup still overlaps
    result = s.run_story(config, RUN, runner, engine=engine)
    assert result.ok and runner.peak == 2
    seen = kinds(repo)
    assert seen.index("task_merged") > [i for i, k in enumerate(seen) if k == "task_started"][1]
    assert story_files(tmp_path) == {"a.py", "b.py"}


def test_the_parallel_limit_is_respected(tmp_path):
    repo, config, engine = project(tmp_path, together=True, max_parallel=1)
    runner = HoldingRunner(hold=0.2)
    assert s.run_story(config, RUN, runner, engine=engine).ok and runner.peak == 1


def test_a_task_that_is_not_parallel_safe_runs_alone(tmp_path):
    repo, config, engine = project(tmp_path, depends=False)  # independent, but not parallel-safe
    runner = HoldingRunner(hold=0.2)
    assert s.run_story(config, RUN, runner, engine=engine).ok and runner.peak == 1


def test_a_task_that_crashes_stops_alone_and_the_others_carry_on(tmp_path):
    repo, config, engine = project(tmp_path, together=True)

    class Crashing(HoldingRunner):
        def run(self, request):
            if request.agent == "builder" and "SMT-62" in str(request.cwd):
                raise RuntimeError("the machine fell over")
            return super().run(request)

    result = s.run_story(config, RUN, Crashing(hold=0.1), engine=engine)
    assert result.statuses() == {"SMT-62": NEEDS_PERSON, "SMT-63": MERGED}
    assert "the machine fell over" in result.tasks["SMT-62"].detail
