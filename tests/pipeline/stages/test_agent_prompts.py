from pathlib import Path

from pipeline.checks.decide import VerifyResult
from pipeline.stages import agent_requests as r
from pipeline.stages import tester_prompt as tp
from pipeline.stages.reviewer_prompt import MAX_DIFF, reviewer_prompt

TASK = {
    "id": "T1", "jira_key": "SMT-62", "title": "Dark theme", "complexity": "medium",
    "description": "d", "acceptance_criteria": ["A is dark", "B is dark"],
    "expected_outcome": "Everything is dark.", "files": ["src/a.js"],
    "verification": ["npm run build", "npm test"],
}  # fmt: skip
COMMANDS = {"setup": ["npm ci"], "project_checks": ["npm test", "npm run lint"]}


def test_the_tester_message_numbers_the_criteria_and_lists_the_test_lines_once():
    text = tp.tester_prompt(TASK, COMMANDS, ["src/a.js", "src/b.js"], "**Changed:** a")
    assert "1. A is dark" in text and "2. B is dark" in text
    assert "- src/b.js" in text and "**Changed:** a" in text
    assert tp.check_lines(TASK, COMMANDS) == ["npm run build", "npm test", "npm run lint"]
    assert text.count("- npm test") == 1


def test_the_tester_message_survives_missing_pieces():
    text = tp.tester_prompt({**TASK, "verification": []}, {}, [], "")
    assert "(no report)" in text and "(none listed)" in text and "- (none)" in text


def verify(**kw):
    return VerifyResult(**{"line": "npm run lint", "passed": False, "exit_code": 1, **kw})


def review(**kw):
    base = dict(
        changed=["src/a.js"], extra=[], verify=[], baseline_tails={}, tester_lines=[],
        diff="+x", builder_report="done",
    )  # fmt: skip
    return reviewer_prompt(TASK, **{**base, **kw})


def test_the_reviewer_sees_the_baseline_output_of_a_check_that_failed_before():
    text = review(
        verify=[verify(baseline_failed=True, output_tail="43 problems now")],
        baseline_tails={"npm run lint": "43 problems then"},
    )
    assert "also failed before the Builder" in text
    assert "43 problems now" in text and "43 problems then" in text


def test_a_new_failure_is_marked_new_and_a_pass_is_just_listed():
    text = review(
        verify=[
            verify(line="npm run build", baseline_failed=False, output_tail="boom"),
            verify(line="npm test", passed=True, exit_code=0),
            verify(line="slow", timed_out=True, exit_code=None),
        ]
    )
    assert "this failure is new" in text and "`npm test`: passed" in text
    assert "did not finish in time" in text


def test_a_long_diff_is_cut_with_a_note_and_empty_input_is_marked():
    assert "diff cut at" in review(diff="x" * (MAX_DIFF + 10))
    assert "No Tester ran" in review() and "(the task lists no check commands" in review()
    assert "Not in the task's Files list: z.js" in review(extra=["z.js"])


def test_the_reviewer_can_only_read_and_the_tester_can_edit(tmp_path):
    root = tmp_path / "proj"
    args = (TASK, "prompt", tmp_path / "wt", root, "sid")
    reviewer = r.reviewer_request(*args)
    assert reviewer.tools == ("Read", "Grep", "Glob") and reviewer.permission_mode == "dontAsk"
    assert reviewer.allowed_bash == () and reviewer.agent_file == r.REVIEWER_FILE
    assert reviewer.cwd == tmp_path / "wt" and any(".env" in rule for rule in reviewer.deny)
    tester = r.tester_request(TASK, COMMANDS, *args[1:])
    assert "Edit" in tester.tools and tester.permission_mode == "acceptEdits"
    assert "npm test" in tester.allowed_bash and tester.agent_file == r.TESTER_FILE
    assert tester.max_turns and tester.max_budget_usd and tester.model == "sonnet"
    assert Path(r.TESTER_FILE).is_file() and Path(r.REVIEWER_FILE).is_file()
    assert r.reviewer_request(*args, resume=True).resume is True
