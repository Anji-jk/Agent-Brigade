"""What planning used (tokens and seconds) is kept, next to its cost, for the Overview tab."""

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from core.db import get_session, init_db
from core.db.repositories import story_runs
from tests.backend.test_planning_api import make_world, plan
from tests.core.db.test_upgrade import old_database
from tests.pipeline.planning.planning_setup import GOOD, planned


def test_the_plan_records_the_tokens_and_seconds_of_every_round(tmp_path):
    result, *_ = planned(tmp_path)
    planner = result.record["planner"]
    assert (planner["input_tokens"], planner["output_tokens"], planner["cache_tokens"]) == (
        120,
        30,
        4000,
    )
    assert planner["duration_seconds"] == 1.5


def test_a_planned_run_keeps_its_usage_in_the_database(tmp_path):
    app, *_ = make_world(tmp_path, GOOD)
    with TestClient(app) as client:
        assert client.post("/api/tracker/sync").status_code == 200
        run_id = plan(client)["run_id"]
        engine = app.state.engine
    with get_session(engine) as session:
        row = story_runs.get_run(session, 1, run_id)
        assert row is not None and row.cost is not None
        assert (row.plan_input_tokens, row.plan_output_tokens, row.plan_cache_tokens) == (
            120,
            30,
            4000,
        )
        assert row.plan_seconds == 1.5 and float(row.cost) == 0.01


def test_an_older_database_gets_the_new_columns_and_old_plans_stay_empty(tmp_path):
    engine = init_db(old_database(tmp_path))
    names = {c["name"] for c in inspect(engine).get_columns("story_runs")}
    assert {"plan_input_tokens", "plan_output_tokens", "plan_cache_tokens", "plan_seconds"} <= names
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT plan_input_tokens, plan_seconds FROM story_runs"
        ).one()
    assert tuple(row) == (None, None)
    engine.dispose()
