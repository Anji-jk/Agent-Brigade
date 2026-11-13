import json

import pytest

from pipeline.stages import prepare as p
from pipeline.workspace.git import commit_of
from tests.pipeline.stages.stage_setup import (
    FAIL,
    MAKE_FILE,
    NO_TESTS,
    OK,
    RUN,
    approved_project,
)
from tests.pipeline.workspace.repo import git


def test_only_an_approved_plan_is_prepared(tmp_path):
    _, config, _ = approved_project(tmp_path, status="waiting")
    with pytest.raises(p.PrepareError, match="is waiting: approve its plan"):
        p.prepare_story(config, RUN)
    assert not (tmp_path / "bw").exists()


def test_the_story_branch_worktree_setup_and_baseline(tmp_path):
    repo, config, base = approved_project(tmp_path, setup=[MAKE_FILE], checks=[OK, NO_TESTS])
    before = git(repo, "status", "--porcelain"), git(repo, "branch", "--show-current")
    prepared, report = p.prepare_story(config, RUN)
    assert prepared.ok and prepared.branch == f"agent/{RUN}" and prepared.base_commit == base
    assert git(repo, "rev-parse", f"agent/{RUN}") == base
    assert (tmp_path / "bw" / RUN / "story" / "made.txt").exists()  # setup ran there
    assert [s.status for s in prepared.setup] == ["ok"]
    assert [s.status for s in prepared.baseline] == ["ok", "warning"]  # exit 5 = no tests yet
    assert prepared.leftovers == ["made.txt"]
    assert (git(repo, "status", "--porcelain"), git(repo, "branch", "--show-current")) == before
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert report == repo / ".agent-brigade" / "runs" / RUN / "build" / "prepare.json"
    assert saved["ok"] is True and saved["baseline"][1]["status"] == "warning"


def test_a_run_is_prepared_once(tmp_path):
    _, config, _ = approved_project(tmp_path)
    p.prepare_story(config, RUN)
    with pytest.raises(p.PrepareError, match="already exists.*clean"):
        p.prepare_story(config, RUN)


def test_a_failing_setup_line_stops_before_the_baseline(tmp_path):
    _, config, _ = approved_project(tmp_path, setup=[FAIL, OK], checks=[OK])
    prepared, _ = p.prepare_story(config, RUN)
    assert not prepared.ok
    assert [s.status for s in prepared.setup] == ["failed"] and prepared.baseline == []
    assert (tmp_path / "bw" / RUN / "story").is_dir()  # kept, to look at


def test_a_failing_baseline_line_does_not_hide_the_others(tmp_path):
    _, config, _ = approved_project(tmp_path, checks=[FAIL, OK])
    prepared, _ = p.prepare_story(config, RUN)
    assert not prepared.ok
    assert [s.status for s in prepared.baseline] == ["failed", "ok"]
    assert prepared.baseline[0].exit_code == 3


def test_a_line_runs_through_the_shell_and_a_missing_program_is_a_failed_line(tmp_path):
    _, config, _ = approved_project(tmp_path, checks=[f"{OK} && {OK}", "no-such-program-xyz"])
    prepared, _ = p.prepare_story(config, RUN)
    assert [s.status for s in prepared.baseline] == ["ok", "failed"]
    assert "no-such-program-xyz" in prepared.baseline[1].output_tail


def test_a_base_commit_that_is_gone_is_refused(tmp_path):
    repo, config, _ = approved_project(tmp_path)
    plan_file = repo / ".agent-brigade" / "runs" / RUN / "plan.json"
    record = json.loads(plan_file.read_text(encoding="utf-8"))
    record["config"]["base_commit"] = "0" * 40
    plan_file.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(p.PrepareError, match="base commit .* is not in the project"):
        p.prepare_story(config, RUN)


# ---------- one attempt of one sub-task ----------


def test_an_attempt_starts_at_the_story_tip_with_its_own_branch_and_setup(tmp_path):
    repo, config, base = approved_project(tmp_path, setup=[MAKE_FILE])
    p.prepare_story(config, RUN)
    ready = p.prepare_attempt(config, RUN, "SMT-62", 1)
    assert ready.ok and ready.start_commit == base
    assert ready.branch == f"agent-attempt/{RUN}/SMT-62-1"
    assert (tmp_path / "bw" / RUN / "SMT-62-1" / "made.txt").exists()
    again = p.prepare_attempt(config, RUN, "SMT-62", 2)  # a retry gets a fresh one
    assert again.worktree != ready.worktree
    assert commit_of(repo, f"refs/heads/{again.branch}") == base


def test_an_attempt_needs_a_known_task_and_a_prepared_run(tmp_path):
    _, config, _ = approved_project(tmp_path)
    with pytest.raises(p.PrepareError, match="no story branch yet"):
        p.prepare_attempt(config, RUN, "SMT-62", 1)
    p.prepare_story(config, RUN)
    with pytest.raises(p.PrepareError, match="SMT-99 is not a task"):
        p.prepare_attempt(config, RUN, "SMT-99", 1)
    p.prepare_attempt(config, RUN, "SMT-62", 1)
    with pytest.raises(p.PrepareError, match="already exists"):
        p.prepare_attempt(config, RUN, "SMT-62", 1)


# ---------- clean ----------


def test_clean_removes_the_worktrees_and_keeps_the_branches(tmp_path):
    repo, config, base = approved_project(tmp_path)
    p.prepare_story(config, RUN)
    p.prepare_attempt(config, RUN, "SMT-62", 1)
    done = p.clean_run(config, RUN)
    assert [line.split()[0] for line in done] == ["removed", "removed"]
    assert "story" in done[-1]  # the story worktree goes last
    assert git(repo, "worktree", "list").count("\n") == 0  # only the main folder is left
    assert git(repo, "rev-parse", f"agent/{RUN}") == base
    assert commit_of(repo, f"refs/heads/agent-attempt/{RUN}/SMT-62-1") == base


def test_clean_keeps_a_worktree_with_work_in_it_unless_discarded(tmp_path):
    _, config, _ = approved_project(tmp_path, setup=[MAKE_FILE])
    p.prepare_story(config, RUN)
    kept = p.clean_run(config, RUN)
    assert kept[0].startswith("kept") and "uncommitted" in kept[0]
    assert (tmp_path / "bw" / RUN / "story").exists()
    assert p.clean_run(config, RUN, discard_changes=True)[0].startswith("removed")
    assert "no worktrees" in p.clean_run(config, RUN)[0]
