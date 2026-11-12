import pytest

from pipeline.planning import story_plan as sp
from pipeline.planning.plan_fields import PlanValidationError
from pipeline.planning.plan_file import validate_tasks
from tests.pipeline.planning.story_samples import ANSWER, answer, entry, story


def merge(the_answer=ANSWER, the_story=None, docs_dir="docs"):
    return sp.merge_planner_output(the_story or story(), the_answer, docs_dir)


def test_a_good_answer_becomes_the_plan_and_records_only_new_jira_links():
    result = merge()
    t1, t2, t3 = result["tasks"]
    assert result["summary"].startswith("Formatter first")
    assert t1["files"] == ["backend/export/csv.py", "tests/test_csv.py"]
    assert t1["doc_target"] == "docs/export.md"
    assert t1["context"] == {"read_first": ["CLAUDE.md", "backend/models.py"], "notes": "Use csv."}
    assert t2["depends_on"] == ["T1"]
    assert t2["dependency_reasons"] == {"T1": "Jira: SMT-58 is blocked by SMT-57"}
    assert t3["depends_on"] == ["T2"]
    assert t3["dependency_reasons"] == {"T2": "It documents the endpoint SMT-58 adds."}
    assert result["jira_links"] == [
        {
            "subtask": "SMT-59",
            "blocked_by": "SMT-58",
            "reason": "It documents the endpoint SMT-58 adds.",
        }
    ]
    assert result["notes"] == []


def test_the_planner_cannot_change_jira_owned_fields():
    changed = answer(
        SMT_57={
            "title": "Changed",
            "acceptance_criteria": ["weaker"],
            "jira_key": "SMT-99",
            "description": "changed",
        }
    )
    task = merge(changed)["tasks"][0]
    assert task["title"] == "Write the skills CSV formatter"
    assert task["jira_key"] == "SMT-57"
    assert task["description"].startswith("Write the skills CSV formatter.")
    assert task["acceptance_criteria"] == [
        "Skill, level and date columns.",
        "Commas in names are quoted.",
    ]


def test_a_jira_dependency_the_planner_left_out_is_put_back():
    result = merge(answer(SMT_58={"depends_on": []}))
    assert result["tasks"][1]["depends_on"] == ["T1"]
    assert "a Jira link the planner left out, put back" in result["notes"][0]
    assert result["jira_links"] == ANSWER_LINKS


ANSWER_LINKS = [
    {
        "subtask": "SMT-59",
        "blocked_by": "SMT-58",
        "reason": "It documents the endpoint SMT-58 adds.",
    }
]


def test_the_planners_reason_for_a_jira_link_is_kept():
    result = merge(answer(SMT_58={"dependency_reasons": {"SMT-57": "Needs the formatter."}}))
    assert result["tasks"][1]["dependency_reasons"] == {"T1": "Needs the formatter."}
    assert result["jira_links"] == ANSWER_LINKS  # still not a new link


def test_every_missing_duplicate_and_unknown_entry_is_reported_at_once():
    bad = {
        "tasks": [
            entry("SMT-57"),
            entry("SMT-57"),
            entry("SMT-77"),
            {"files": []},
            entry("SMT-58", depends_on=["SMT-59"]),
        ]
    }
    with pytest.raises(PlanValidationError) as caught:
        merge(bad)
    text = str(caught.value)
    for part in (
        "SMT-57 is planned twice",
        "SMT-77 is not an open sub-task of SMT-56",
        "Entry 4 names no sub-task",
        "SMT-59 has no entry",
        "SMT-58 depends on SMT-59 without a reason",
    ):
        assert part in text


def test_bad_dependencies_are_refused():
    with pytest.raises(PlanValidationError, match="not another open sub-task"):
        merge(answer(SMT_59={"depends_on": ["SMT-59"], "dependency_reasons": {"SMT-59": "x"}}))
    with pytest.raises(PlanValidationError, match="not a sub-task key"):
        merge(answer(SMT_59={"depends_on": [7]}))
    with pytest.raises(PlanValidationError, match="depends_on must be a list"):
        merge(answer(SMT_59={"depends_on": "SMT-58"}))
    with pytest.raises(PlanValidationError, match="no task list"):
        merge({"summary": "x"})


def test_done_subtasks_are_left_out_with_notes():
    with_done = {"tasks": [*ANSWER["tasks"], entry("SMT-60")]}
    assert "SMT-60 is done in Jira" in merge(with_done)["notes"][0]
    on_done = answer(SMT_59={"depends_on": ["SMT-60"], "dependency_reasons": {"SMT-60": "x"}})
    result = merge(on_done)
    assert result["tasks"][2]["depends_on"] == []
    assert "already done in Jira" in result["notes"][0]


def test_cycles_sizes_paths_and_empty_outcomes_are_refused():
    loop = answer(SMT_57={"depends_on": ["SMT-59"], "dependency_reasons": {"SMT-59": "x"}})
    with pytest.raises(PlanValidationError, match="cycle"):
        merge(loop)
    with pytest.raises(PlanValidationError, match="complexity"):
        merge(answer(SMT_57={"complexity": "huge"}))
    with pytest.raises(PlanValidationError, match="inside the repository"):
        merge(answer(SMT_57={"files": ["../outside.py"]}))
    with pytest.raises(PlanValidationError, match="expected_outcome"):
        merge(answer(SMT_57={"expected_outcome": ""}))


def test_tasks_sharing_files_are_made_one_at_a_time():
    shared = answer(
        SMT_57={"parallel_safe": True, "files": ["README.md"]},
        SMT_59={
            "parallel_safe": True,
            "depends_on": [],
            "dependency_reasons": {},
            "files": ["README.md"],
        },
    )
    result = merge(shared)
    assert not result["tasks"][0]["parallel_safe"]
    assert any("runs one at a time" in note for note in result["notes"])


def test_doc_targets_must_be_in_the_docs_folder():
    with pytest.raises(PlanValidationError, match="not in the docs folder docs/"):
        merge(answer(SMT_57={"doc_target": "notes/export.md"}))
    result = merge(docs_dir="")
    assert result["tasks"][0]["doc_target"] is None
    assert "no docs folder is set" in result["notes"][0]


def test_merged_tasks_pass_validation_unchanged():
    tasks = merge()["tasks"]
    assert validate_tasks(tasks) == tasks
