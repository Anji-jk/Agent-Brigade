import json

import pytest

from pipeline.planning import plan_file as pf
from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_file import PlanFileError


def task(task_id="T1", **overrides):
    value = {
        "id": task_id,
        "title": f"Do {task_id}",
        "description": "Details.",
        "depends_on": [],
        "expected_outcome": "It works.",
        "files": [f"src/{task_id}.py"],
        "verification": ["python -m pytest"],
        "acceptance_criteria": ["It works."],
        "complexity": "small",
        "parallel_safe": False,
    }
    value.update(overrides)
    return value


def document(*tasks):
    return {
        "source": {"kind": "jira", "key": "SMT-56"},
        "summary": "Approach.",
        "tasks": list(tasks or [task()]),
        "approval": {"status": "waiting", "jira_links": []},
    }


# ---------- validate_tasks ----------


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([], "non-empty list"),
        ("T1", "non-empty list"),
        ([task(str(n)) for n in range(31)], "at most 30"),
    ],
)
def test_the_task_list_must_be_a_list_of_one_to_thirty(tasks, message):
    with pytest.raises(PlanValidationError, match=message):
        pf.validate_tasks(tasks)


def test_tasks_are_normalized_and_checked_against_each_other():
    tasks = pf.validate_tasks(
        [
            task("T1", complexity=" Large ", parallel_safe=True, files=["a.py"]),
            task("T2", parallel_safe=True, files=["a.py"]),
        ]
    )
    assert tasks[0]["complexity"] == "large"
    assert [t["parallel_safe"] for t in tasks] == [False, False]  # share a.py, unordered
    with pytest.raises(PlanValidationError, match="cycle"):
        pf.validate_tasks([task("T1", depends_on=["T2"]), task("T2", depends_on=["T1"])])


# ---------- parse_planner_answer ----------


@pytest.mark.parametrize(
    "text",
    [
        '{"tasks": []}',
        'Here it is:\n```json\n{"tasks": []}\n```\nDone.',
        'Sure! {"tasks": []} Let me know.',
    ],
)
def test_the_answer_is_found_bare_fenced_or_amid_prose(text):
    assert pf.parse_planner_answer(text) == {"tasks": []}


@pytest.mark.parametrize("text", [None, "", "   ", "no json here", "[1, 2]"])
def test_an_answer_without_an_object_is_refused(text):
    with pytest.raises(PlanValidationError):
        pf.parse_planner_answer(text)


# ---------- saving and loading ----------


def test_a_saved_plan_is_read_back_checked(tmp_path):
    path = pf.save_plan(tmp_path, "run-1", document(task(complexity="LARGE")))
    assert path == tmp_path / ".agent-brigade" / "runs" / "run-1" / "plan.json"
    record = pf.load_plan(tmp_path, "run-1")
    assert record["schema_version"] == 2
    assert record["run_id"] == "run-1" and record["created_at"]
    assert record["tasks"][0]["complexity"] == "large"
    assert record["source"]["key"] == "SMT-56"


def test_the_first_save_hides_the_folder_from_git(tmp_path):
    pf.save_plan(tmp_path, "run-1", document())
    assert (tmp_path / ".agent-brigade" / ".gitignore").read_text() == "*\n"


def test_a_plan_is_never_overwritten(tmp_path):
    pf.save_plan(tmp_path, "run-1", document())
    with pytest.raises(FileExistsError):
        pf.save_plan(tmp_path, "run-1", document(task(title="Other")))
    assert pf.load_plan(tmp_path, "run-1")["tasks"][0]["title"] == "Do T1"


def test_an_invalid_plan_is_not_written(tmp_path):
    with pytest.raises(PlanValidationError):
        pf.save_plan(tmp_path, "run-1", document(task(complexity="huge")))
    assert not pf.plan_path(tmp_path, "run-1").exists()


def test_a_bad_run_id_never_becomes_a_path(tmp_path):
    with pytest.raises(ValueError, match="Not a run id"):
        pf.save_plan(tmp_path, "../escape", document())


def write(tmp_path, record, run_id="run-1"):
    path = pf.plan_path(tmp_path, run_id)
    path.parent.mkdir(parents=True)
    path.write_text(record if isinstance(record, str) else json.dumps(record), encoding="utf-8")


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ("{not json", "unreadable or malformed"),
        ({"run_id": "run-2", "schema_version": 2}, "does not match its run id"),
        ({"run_id": "run-1", "schema_version": 1}, "schema version: 1"),
        ({"run_id": "run-1", "schema_version": 2, "tasks": []}, "Stored plan is invalid"),
    ],
)
def test_a_bad_stored_plan_is_refused(tmp_path, record, message):
    write(tmp_path, record)
    with pytest.raises(PlanFileError, match=message):
        pf.load_plan(tmp_path, "run-1")


def test_a_missing_plan_is_named(tmp_path):
    with pytest.raises(PlanFileError, match="No plan found for run run-1"):
        pf.load_plan(tmp_path, "run-1")


def test_approval_changes_only_the_approval_block(tmp_path):
    pf.save_plan(tmp_path, "run-1", document())
    before = pf.load_plan(tmp_path, "run-1")
    after = pf.save_approval(tmp_path, "run-1", {"status": "approved", "jira_links": []})
    assert after["approval"] == {"status": "approved", "jira_links": []}
    assert {k: v for k, v in after.items() if k != "approval"} == {
        k: v for k, v in before.items() if k != "approval"
    }


def test_approval_needs_a_plan_that_waits_for_it(tmp_path):
    pf.save_plan(tmp_path, "run-1", {**document(), "approval": None})
    with pytest.raises(PlanFileError, match="not a plan that waits for approval"):
        pf.save_approval(tmp_path, "run-1", {"status": "approved"})
