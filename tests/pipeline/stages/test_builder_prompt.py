from pipeline.stages.builder_prompt import builder_prompt
from tests.pipeline.planning.test_plan_file import task


def full_task():
    return task(
        "T1",
        jira_key="SMT-62",
        title="Add the toggle",
        description="Put a toggle in the header.",
        acceptance_criteria=["Toggle is visible", "Choice is kept"],
        expected_outcome="Users can switch.",
        files=["frontend/src/App.jsx"],
        verification=["cd frontend && npm run build"],
        context={"read_first": ["frontend/src/index.css"], "notes": "Use the existing tokens."},
    )


def test_the_prompt_holds_only_this_task_in_the_right_order():
    text = builder_prompt(full_task())
    headings = [
        "# SMT-62: Add the toggle",
        "## Description",
        "## Accept",
        "## Outcome",
        "## Files you are expected to change",
        "## Read first",
        "## Notes",
        "## Commands",
    ]
    places = [text.index(x) for x in headings]
    assert places == sorted(places)
    facts = [
        "- Toggle is visible",
        "- Choice is kept",
        "- frontend/src/App.jsx",
        "- frontend/src/index.css",
        "Use the existing tokens.",
        "- cd frontend && npm run build",
    ]
    assert all(fact in text for fact in facts)
    assert "Feedback" not in text


def test_feedback_comes_first_and_missing_parts_are_said_so():
    bare = task("T2", files=[], verification=[])
    text = builder_prompt(bare, feedback="The button has no label.")
    assert text.startswith("## Feedback from the earlier attempt")
    assert "The button has no label." in text
    assert "(the plan names none" in text and "(none listed)" in text
    assert "(nothing named" in text


def test_long_text_is_cut():
    long = task("T3", description="x" * 5000)
    assert "(cut short)" in builder_prompt(long)
