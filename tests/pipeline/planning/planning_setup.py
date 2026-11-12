"""A ready Skill Matrix style project, settings for it, and a fake Planner, for planning tests."""

import json

from pipeline.planning.planner import plan_story
from tests.doubles.claude import FakeClaude
from tests.doubles.jira import FakeJira
from tests.pipeline.planning.story_samples import ANSWER, story
from tests.pipeline.planning.test_readiness import PASS, ready_project, settings

GOOD = json.dumps(ANSWER)


def project(tmp_path):
    """(repo, settings): a clean checkout on main with CLAUDE.md, docs/ and passing tests."""
    repo = ready_project(tmp_path)
    return repo, settings(tmp_path, project_path=repo, docs_dir="docs", test_command=PASS)


def planner(tmp_path, *answers):
    # A short folder name keeps the transcript path under the Windows 260-character limit.
    return FakeClaude(tmp_path / "ch", *answers)


def planned(tmp_path, *answers, **options):
    """Plan SMT-56 with these answers: (result, fake planner, repo)."""
    repo, the_settings = project(tmp_path)
    fake = planner(tmp_path, *(answers or (GOOD,)))
    result = plan_story(story(), the_settings, fake, **options)
    return result, fake, repo


def jira_board():
    """The sample story SMT-56 as Jira holds it: SMT-58 already waits for SMT-57."""
    criteria = "Acceptance criteria:\n- It works."
    return (
        FakeJira()
        .add("SMT-2", "epic", "Profiles")
        .add("SMT-56", "story", "Export a person's skills", "SMT-2", "Managers want a spreadsheet.")
        .add("SMT-57", "sub-task", "Write the skills CSV formatter", "SMT-56", criteria)
        .add("SMT-58", "sub-task", "Add the export endpoint", "SMT-56", criteria)
        .add("SMT-59", "sub-task", "Document the export", "SMT-56", criteria)
        .add("SMT-60", "sub-task", "Old spike", "SMT-56", criteria, status="Done", done=True)
        .block("SMT-58", "SMT-57")
    )
