import pytest

from pipeline.planning.plan_fields import PlanValidationError, check_task


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


def validate_tasks(raws):
    return [check_task(raw, index) for index, raw in enumerate(raws, start=1)]


def test_optional_fields_default_to_empty_and_unknown_fields_are_dropped():
    minimal = {
        "id": "T1",
        "title": "t",
        "description": "d",
        "expected_outcome": "o",
        "acceptance_criteria": ["c"],
        "complexity": " Medium ",
        "evil": "rm -rf /",
    }
    (checked,) = validate_tasks([minimal])
    assert checked["complexity"] == "medium"
    assert checked["depends_on"] == checked["files"] == checked["verification"] == []
    assert checked["parallel_safe"] is False
    assert "evil" not in checked


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        (["x"], "must be an object"),
        ([task("bad id")], "invalid id"),
        ([task(title="")], "title must not be empty"),
        ([task(title="x" * 201)], "longer than 200"),
        ([task(acceptance_criteria=[])], "at least one acceptance criterion"),
        ([task(complexity="huge")], "complexity must be one of"),
        ([task(parallel_safe="yes")], "true or false"),
        ([task(files="a.py")], "list of at most 30"),
        ([task(files=[3])], "must be text"),
    ],
)
def test_bad_tasks_are_refused(tasks, message):
    with pytest.raises(PlanValidationError, match=message):
        validate_tasks(tasks)


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "C:\\x.py", "~/x", "\\\\server\\x", "../x.py", "a/../../x"]
)
def test_paths_outside_the_repository_are_refused(path):
    with pytest.raises(PlanValidationError, match="inside the repository"):
        validate_tasks([task(files=[path])])
    with pytest.raises(PlanValidationError, match="inside the repository"):
        validate_tasks([task(context={"read_first": [path]})])


def test_story_fields_are_checked():
    good = task(
        jira_key="SMT-57",
        dependency_reasons={},
        doc_target="docs/a.md",
        context={"read_first": ["CLAUDE.md"], "notes": None},
    )
    (checked,) = validate_tasks([good])
    assert checked["context"] == {"read_first": ["CLAUDE.md"], "notes": ""}
    with pytest.raises(PlanValidationError, match="invalid jira_key"):
        validate_tasks([task(jira_key="smt-1")])
    with pytest.raises(PlanValidationError, match="context must be an object"):
        validate_tasks([task(context="read it")])
