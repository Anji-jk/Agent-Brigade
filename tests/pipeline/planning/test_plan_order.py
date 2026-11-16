import pytest

from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_order import check_order, overlapping_tasks


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


def ordered(*tasks):
    """The tasks checked together, the way a plan's list is; returns them."""
    check_order(list(tasks))
    return list(tasks)


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([task(), task()], "Duplicate task ids: T1"),
        ([task("T1", jira_key="SMT-57"), task("T2", jira_key="SMT-57")], "in two tasks: SMT-57"),
        ([task(depends_on=["T1"])], "depends on itself"),
        ([task(depends_on=["T9"])], "missing task 'T9'"),
        ([task("T1"), task("T2", depends_on=["T1", "T1"])], "lists a dependency twice"),
        ([task(dependency_reasons={"T9": "x"})], "reason for a task it does not depend on"),
        ([task("T1", depends_on=["T2"]), task("T2", depends_on=["T1"])], "cycle: T1, T2"),
    ],
)
def test_bad_task_relations_are_refused(tasks, message):
    with pytest.raises(PlanValidationError, match=message):
        check_order(tasks)


def test_a_chain_is_accepted():
    ordered(task("T1"), task("T2", depends_on=["T1"]), task("T3", depends_on=["T2"]))


def safe_flags(*tasks):
    return [t["parallel_safe"] for t in ordered(*tasks)]


def test_parallel_safe_is_kept_only_when_files_do_not_overlap():
    flags = safe_flags(
        task("T1", parallel_safe=True, files=["a.py"]),
        task("T2", parallel_safe=True, files=["b.py"]),
        task("T3", parallel_safe=True, files=["./A.py"]),  # the same file as T1
        task("T4", parallel_safe=True, files=["a.py"], depends_on=["T3"]),
    )
    assert flags == [False, True, False, False]


def test_ordered_tasks_may_share_files():
    assert safe_flags(
        task("T1", parallel_safe=True, files=["a.py"]),
        task("T2", parallel_safe=True, files=["a.py"], depends_on=["T1"]),
    ) == [True, True]


def test_a_task_without_files_is_never_safe():
    assert safe_flags(task("T1", parallel_safe=True, files=[]), task("T2", parallel_safe=True)) == [
        False,
        False,
    ]


def test_a_task_not_claimed_safe_stays_unsafe():
    assert safe_flags(task("T1", files=["a.py"]), task("T2", files=["b.py"])) == [False, False]


def test_overlapping_tasks_are_those_unordered_tasks_that_may_share_files():
    tasks = [
        task("T1", files=["a.py", "b.py"]),
        task("T2", files=["B.py", "c.py"]),  # shares b.py with T1 (case does not matter)
        task("T3", files=["d.py"]),
        task("T4", files=["a.py"], depends_on=["T1"]),  # ordered after T1: never overlaps it
        task("T5", files=[]),  # names no files: may overlap anything it is not ordered against
    ]
    assert overlapping_tasks(tasks, "T1") == {"T2": ["b.py"], "T5": []}
    assert overlapping_tasks(tasks, "T3") == {"T5": []}
    assert overlapping_tasks(tasks, "T4") == {"T5": []}  # T1 shares a.py but comes before it
