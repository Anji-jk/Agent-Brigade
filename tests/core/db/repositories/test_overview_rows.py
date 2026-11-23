from datetime import datetime

import pytest

from core.db import get_session, init_db, make_engine
from core.db.models import AgentRun, Attempt, Merge, Project, StoryRun, SubTask, TrackerItem
from core.db.repositories import overview_rows as o

T0, T1, T2 = (
    datetime(2026, 11, 13, 10),
    datetime(2026, 11, 13, 10, 5),
    datetime(2026, 11, 13, 10, 30),
)


def agent(attempt, role, cost, tokens, seconds, model="sonnet"):
    return AgentRun(
        attempt_id=attempt.id,
        role=role,
        model_used=model,
        cost=cost,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        cache_tokens=tokens[2],
        duration_s=seconds,
    )


@pytest.fixture
def engine(tmp_path):
    """One built run (SMT-62 needs two attempts, SMT-63 one), a plan never built, a new plan."""
    engine = init_db(make_engine(tmp_path / "brigade.db"))
    with get_session(engine) as s:
        s.add(Project(id=1, name="SM", local_path="C:/sm", base_branch="main"))
        s.add(Project(id=2, name="Other", local_path="C:/other", base_branch="main"))
        s.flush()
        for key, kind in (("SMT-61", "story"), ("SMT-62", "sub-task"), ("SMT-63", "sub-task")):
            s.add(TrackerItem(key=key, project_id=1, type=kind, summary=f"title of {key}"))
        s.flush()
        built = StoryRun(project_id=1, story_key="SMT-61", run_id="SMT-61-A", status="approved")
        built.cost, built.started_at = 0.5, T0  # planned with nothing kept but the cost
        plan_only = StoryRun(project_id=1, story_key="SMT-61", run_id="SMT-61-B", status="waiting")
        plan_only.cost, plan_only.started_at = 0.25, T0
        new_plan = StoryRun(project_id=1, story_key="SMT-61", run_id="SMT-61-C", status="waiting")
        new_plan.cost, new_plan.started_at = 0.25, T0
        new_plan.plan_input_tokens, new_plan.plan_output_tokens = 100, 20
        new_plan.plan_cache_tokens, new_plan.plan_seconds = 3000, 40.0
        elsewhere = StoryRun(project_id=2, story_key="SMT-61", run_id="X-1", status="waiting")
        elsewhere.cost = 9.0
        s.add_all([built, plan_only, new_plan, elsewhere])
        s.flush()
        first = SubTask(story_run_id=built.id, key="SMT-62", status="done")
        second = SubTask(story_run_id=built.id, key="SMT-63", status="error")
        s.add_all([first, second])
        s.flush()
        failed = Attempt(sub_task_id=first.id, number=1, outcome="failed")
        failed.started_at, failed.ended_at = T0, T1
        fixed = Attempt(sub_task_id=first.id, number=2, outcome="done")
        fixed.started_at, fixed.ended_at = T1, T2
        broken = Attempt(sub_task_id=second.id, number=1, outcome="error")
        broken.started_at, broken.ended_at = T1, T2
        s.add_all([failed, fixed, broken])
        s.flush()
        s.add(Merge(attempt_id=fixed.id, kind="fast-forward"))
        s.add_all(
            [
                agent(failed, "builder", 0.1, (10, 20, 300), 60),
                agent(fixed, "builder", 0.2, (10, 20, 300), 120, model="opus"),
                agent(fixed, "reviewer", 0.3, (1, 2, 3), 30),
                agent(broken, "builder", 0.4, (5, 5, 5), 90),
            ]
        )
    yield engine
    engine.dispose()


def test_only_a_plan_that_was_built_is_a_run(engine):
    with get_session(engine) as s:
        assert [(r.run_id, title) for r, title in o.build_runs(s, 1)] == [
            ("SMT-61-A", "title of SMT-61")
        ]
        assert o.build_runs(s, 2) == []


def test_a_run_adds_up_its_tasks_attempts_merges_and_agents(engine):
    with get_session(engine) as s:
        (use,) = o.usage_by_run(s, 1).values()
    assert use.statuses == {"done": 1, "error": 1} and use.tasks == 2
    assert (use.attempts, use.tasks_tried, use.merged) == (3, 2, 1)
    assert use.cost == pytest.approx(1.0)
    assert (use.input_tokens, use.output_tokens, use.cache_tokens) == (26, 47, 608)
    assert use.agent_seconds == 300 and (use.first_start, use.last_end) == (T0, T2)


def test_planning_counts_every_plan_and_keeps_old_ones_apart_from_recorded_ones(engine):
    with get_session(engine) as s:
        planning = o.planning_totals(s, 1)
    assert (planning.plans, planning.recorded) == (3, 1)
    assert planning.cost == pytest.approx(1.0)  # the other project's 9.0 is not here
    assert (planning.input_tokens, planning.output_tokens, planning.cache_tokens) == (100, 20, 3000)
    assert planning.seconds == 40.0


def test_agents_are_grouped_by_role_and_by_model_dearest_first(engine):
    with get_session(engine) as s:
        roles = o.agents_grouped(s, 1, by_model=False)
        models = o.agents_grouped(s, 1, by_model=True)
    assert [(g.name, g.runs) for g in roles] == [("builder", 3), ("reviewer", 1)]
    assert roles[0].cost == pytest.approx(0.7) and roles[0].output_tokens == 45
    assert [(g.name, g.runs) for g in models] == [("sonnet", 3), ("opus", 1)]


def test_an_empty_project_adds_up_to_zero(engine):
    with get_session(engine) as s:
        assert o.usage_by_run(s, 99) == {} and o.agents_grouped(s, 99, by_model=True) == []
        assert o.planning_totals(s, 99) == o.PlanningTotals(0, 0.0, 0, 0, 0, 0, 0)


def test_a_story_is_approved_when_a_plan_of_it_is_approved_or_it_was_built(engine):
    with get_session(engine) as s:
        assert o.stories_approved(s, 1) == 1  # SMT-61: built (its plans may be anything)
        for key in ("SMT-70", "SMT-71"):
            s.add(TrackerItem(key=key, project_id=1, type="story", summary="t"))
        s.flush()
        s.add(StoryRun(project_id=1, story_key="SMT-70", run_id="SMT-70-A", status="approved"))
        s.add(StoryRun(project_id=1, story_key="SMT-71", run_id="SMT-71-A", status="waiting"))
        s.flush()
        assert o.stories_approved(s, 1) == 2  # SMT-70 approved, never built; SMT-71 only waiting
        assert o.stories_approved(s, 99) == 0
