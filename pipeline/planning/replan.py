"""Re-plan: a new plan for the same story, made from the earlier plan and a person's idea.

The earlier plan is never overwritten. The new plan is a new run, its plan.json says which run it
came from and what was asked, and the earlier run is marked replaced so the two can be compared.
A plan that is approved cannot be re-planned: its links are already in Jira, so plan the story
again instead. The budget of the earlier plan carries over unless a new one is given.
"""

from core.settings import Settings
from core.trackers.models import Story
from pipeline.planning.approval import SUPERSEDED, ApprovalError, mark_superseded
from pipeline.planning.plan_file import PlanFileError, load_plan
from pipeline.planning.planner import PlanningError, PlanResult, plan_story
from pipeline.planning.story_plan import APPROVED
from pipeline.runner.claude_runner import AgentRunner
from pipeline.workspace.git import GitError, repository_root


def replan_story(
    story: Story,
    settings: Settings,
    runner: AgentRunner,
    previous_run_id: str,
    changes: str,
    *,
    run_tests: bool = True,
    budget: float | None = None,
    run_id: str | None = None,
) -> PlanResult:
    """Plan `story` again following `changes`; the plan of `previous_run_id` is marked replaced."""
    changes = (changes or "").strip()
    if not changes:
        raise PlanningError("Say what should change: a re-plan needs your idea.")
    if settings.project_path is None:
        raise PlanningError("BRIGADE_PROJECT_PATH is empty in .env.")
    try:
        root = repository_root(settings.project_path)
        previous = load_plan(root, previous_run_id)
    except (GitError, PlanFileError) as exc:
        raise PlanningError(str(exc)) from None
    approval = previous.get("approval") or {}
    if approval.get("status") == APPROVED:
        raise PlanningError(
            f"Run {previous_run_id} is already approved and its links are in Jira, so it cannot "
            "be re-planned. Plan the story again instead."
        )
    if approval.get("status") == SUPERSEDED:
        raise PlanningError(
            f"Run {previous_run_id} was already replaced by {approval.get('superseded_by')}: "
            "re-plan that run instead."
        )
    if previous["source"]["key"] != story.story.key:
        raise PlanningError(
            f"Run {previous_run_id} is a plan for {previous['source']['key']}, "
            f"not for {story.story.key}."
        )
    result = plan_story(
        story,
        settings,
        runner,
        run_tests=run_tests,
        run_id=run_id,
        budget=budget if budget is not None else previous["config"].get("budget_usd"),
        previous=previous,
        changes=changes,
    )
    try:
        mark_superseded(root, previous_run_id, result.run_id)
    except (ApprovalError, PlanFileError) as exc:
        raise PlanningError(
            f"The new plan {result.run_id} is saved, but run {previous_run_id} could not be "
            f"marked replaced: {exc}"
        ) from None
    return result
