import json

from pipeline.feed.step_items import orchestrator_items, story_items


def write(tmp_path, lines, name="events.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def step(name, **fields):
    return {"at": "2026-11-16T09:48:05+00:00", "step": name, **fields}


def test_a_started_step_waits_for_its_finish_and_then_holds_the_outcome(tmp_path):
    started = step("builder_started", model="sonnet", session_id="abc")
    (item,) = orchestrator_items(write(tmp_path, [started]))
    assert item.pending and item.title == "builder" and "model: sonnet" in item.detail
    done = step(
        "builder_finished", ok=True, changed=4, error=None, cost_usd=0.1449, turns=14, seconds=81.2
    )
    (item,) = orchestrator_items(write(tmp_path, [started, done]))
    assert not item.pending
    assert item.result["status"] == "ok"
    assert item.result["summary"] == "4 files changed · $0.1449 · 14 turns · 81.2s"


def test_a_builder_that_failed_shows_its_error(tmp_path):
    lines = [step("builder_started"), step("builder_finished", ok=False, changed=0, error="boom")]
    (item,) = orchestrator_items(write(tmp_path, lines))
    assert item.result["status"] == "error" and item.result["detail"] == "boom"


def test_the_whole_story_of_one_attempt_reads_in_order(tmp_path):
    lines = [
        step("attempt_started", attempt=1),
        step("worktree_ready", branch="agent-attempt/R/SMT-62-1", setup_ok=True),
        step("builder_started", model="sonnet"),
        step("builder_finished", ok=True, changed=1),
        step("checks_finished", passed=True, failures=[]),
        step("tester_finished", ran=False, skipped="the task lists no test file"),
        step("judge_started"),
        step(
            "judge_finished",
            outcome="done",
            reasons=["Every check passed."],
            commit="b86f1a6",
            verdict="pass",
        ),
        step("merge_started"),
        step("merge_finished", merged=True, how="fast-forward"),
    ]
    items = orchestrator_items(write(tmp_path, lines))
    assert [i.title for i in items] == [
        "attempt 1 started",
        "worktree ready on agent-attempt/R/SMT-62-1",
        "builder",
        "checks passed",
        "tester skipped",
        "judge",
        "merge into the story branch",
    ]
    assert [i.index for i in items] == list(range(7))
    assert items[4].detail == "the task lists no test file" and items[4].status == "skipped"
    assert items[5].result["summary"] == "done · verdict pass"
    assert "Every check passed." in items[5].result["detail"]
    assert items[6].result["summary"] == "merged · fast-forward"


def test_failed_checks_list_what_failed(tmp_path):
    (item,) = orchestrator_items(
        write(
            tmp_path,
            [step("checks_finished", passed=False, failures=["scope: a.py", "verify: lint"])],
        )
    )
    assert item.title == "checks failed" and item.status == "error"
    assert item.detail == "- scope: a.py\n- verify: lint"


def test_a_worktree_whose_setup_failed_is_an_error(tmp_path):
    (item,) = orchestrator_items(
        write(tmp_path, [step("worktree_ready", branch="b", setup_ok=False)])
    )
    assert item.status == "error" and "setup failed" in item.title


def test_a_judge_that_did_not_finish_the_task_is_an_error(tmp_path):
    lines = [step("judge_started"), step("judge_finished", outcome="failed", reasons=["scope"])]
    (item,) = orchestrator_items(write(tmp_path, lines))
    assert item.result["status"] == "error" and item.result["summary"] == "failed"


def test_a_merge_that_did_not_happen_is_an_error(tmp_path):
    lines = [step("merge_started"), step("merge_finished", merged=False, error="conflict")]
    (item,) = orchestrator_items(write(tmp_path, lines))
    assert item.result["status"] == "error" and item.result["detail"] == "conflict"


def test_a_tester_that_ran_shows_what_it_wrote(tmp_path):
    lines = [
        step("tester_started", model="sonnet"),
        step("tester_finished", ran=True, error=None, wrote=2, cost_usd=0.05, turns=6),
    ]
    (item,) = orchestrator_items(write(tmp_path, lines))
    assert item.result["summary"] == "2 test files written · $0.0500 · 6 turns"


def test_an_unknown_step_is_still_shown(tmp_path):
    (item,) = orchestrator_items(write(tmp_path, [step("something_new", a=1)]))
    assert item.title == "something new" and '"a": 1' in item.detail


def test_a_line_that_is_not_a_step_is_skipped(tmp_path):
    assert (
        orchestrator_items(write(tmp_path, [{"no": "step"}, step("judge_started")])).__len__() == 1
    )


def test_the_story_log_reads_as_one_line_per_thing_that_happened(tmp_path):
    lines = [
        {"kind": "story_started", "at": "t1", "tasks": 3, "parallel": 3},
        {"kind": "task_started", "at": "t2", "key": "SMT-62", "attempt": 1},
        {"kind": "task_done", "at": "t3", "key": "SMT-62", "attempt": 1},
        {"kind": "task_merged", "at": "t4", "key": "SMT-62", "attempt": 1, "how": "fast-forward"},
        {
            "kind": "task_failed",
            "at": "t5",
            "key": "SMT-63",
            "attempt": 1,
            "reason": "judge: not done",
        },
        {
            "kind": "task_stopped",
            "at": "t6",
            "key": "SMT-64",
            "status": "needs_review",
            "detail": "scope",
        },
        {"kind": "story_finished", "at": "t7", "SMT-62": "merged", "SMT-63": "failed"},
        {"kind": "story_stopped", "at": "t8", "SMT-64": "needs_review"},
    ]
    items = story_items(write(tmp_path, lines, "story-events.jsonl"))
    assert [(i.kind, i.title) for i in items] == [
        ("start", "story started · 3 tasks, up to 3 at once"),
        ("step", "SMT-62 · attempt 1 started"),
        ("step", "SMT-62 · attempt 1 built and judged: done"),
        ("finish", "SMT-62 · merged (fast-forward)"),
        ("error", "SMT-63 · attempt 1 failed: judge: not done"),
        ("error", "SMT-64 · stopped: needs_review"),
        ("finish", "story finished"),
        ("error", "story stopped"),
    ]
    assert items[1].extra["key"] == "SMT-62" and items[5].detail == "scope"
    assert items[6].detail == "SMT-62: merged\nSMT-63: failed"
    assert [i.at for i in items][:2] == ["t1", "t2"]


def test_an_unknown_story_event_is_still_shown(tmp_path):
    (item,) = story_items(write(tmp_path, [{"kind": "odd_thing", "at": "t", "x": 1}]))
    assert item.title == "odd thing"


def test_a_finish_whose_start_is_missing_is_shown_with_its_outcome(tmp_path):
    (item,) = orchestrator_items(write(tmp_path, [step("judge_finished", outcome="done")]))
    assert item.title == "judge" and item.result["summary"] == "done"
    assert not item.pending


def test_a_tester_that_ran_is_not_called_skipped_when_its_start_is_missing(tmp_path):
    (item,) = orchestrator_items(write(tmp_path, [step("tester_finished", ran=True, wrote=1)]))
    assert item.title == "tester" and item.result["summary"] == "1 test file written"
