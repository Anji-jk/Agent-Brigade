"""A Skill Matrix style story with three open sub-tasks and one done, and planner answers."""

import copy

from core.trackers.models import Epic, Story, WorkItem

SITE = "https://example.atlassian.net/browse"


def work_item(key, summary, *, criteria="- It works.", blocked_by=(), done=False, description=None):
    text = (
        description
        if description is not None
        else (f"{summary}.\n\nAcceptance Criteria:\n\n{criteria}" if criteria else summary)
    )
    return WorkItem(
        key=key,
        type="Subtask",
        summary=summary,
        description=text,
        status="Done" if done else "To Do",
        done=done,
        labels=("backend",),
        priority="Medium",
        url=f"{SITE}/{key}",
        acceptance_criteria=criteria or None,
        blocked_by=tuple(blocked_by),
    )


def story(*subtasks):
    main = WorkItem(
        key="SMT-56",
        type="Story",
        summary="Export a person's skills",
        description="Managers want a person's skills in a spreadsheet.",
        status="To Do",
        done=False,
        labels=(),
        priority="High",
        url=f"{SITE}/SMT-56",
    )
    return Story(main, Epic("SMT-2", "Profiles"), tuple(subtasks or SUBTASKS))


SUBTASKS = (
    work_item(
        "SMT-57",
        "Write the skills CSV formatter",
        criteria="- Skill, level and date columns.\n- Commas in names are quoted.",
    ),
    work_item(
        "SMT-58",
        "Add the export endpoint",
        criteria="- GET /skills/export returns the file.",
        blocked_by=("SMT-57",),
    ),
    work_item("SMT-59", "Document the export", criteria="- README shows an example."),
    work_item("SMT-60", "Old spike", done=True),
)


def entry(key, **more):
    return {
        "key": key,
        "depends_on": [],
        "dependency_reasons": {},
        "files": [f"{key}.py"],
        "complexity": "small",
        "parallel_safe": False,
        "expected_outcome": f"{key} done",
        "verification": ["python -m pytest -q"],
        "doc_target": None,
        "context": {"read_first": ["CLAUDE.md"], "notes": ""},
        **more,
    }


ANSWER = {
    "summary": "Formatter first, then the endpoint, then the README.",
    "tasks": [
        entry(
            "SMT-57",
            files=["backend/export/csv.py", "tests/test_csv.py"],
            doc_target="docs/export.md",
            context={"read_first": ["CLAUDE.md", "backend/models.py"], "notes": "Use csv."},
        ),
        entry("SMT-58", depends_on=["SMT-57"], files=["backend/api/export.py"]),
        entry(
            "SMT-59",
            depends_on=["SMT-58"],
            dependency_reasons={"SMT-58": "It documents the endpoint SMT-58 adds."},
            files=["README.md"],
        ),
    ],
}


def answer(**changes):
    """ANSWER with entries changed, such as answer(SMT_58={"files": ["a.py"]})."""
    copied = copy.deepcopy(ANSWER)
    for name, change in changes.items():
        key = name.replace("_", "-")
        for task in copied["tasks"]:
            if task["key"] == key:
                task.update(change)
    return copied
