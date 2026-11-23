import pytest

from core.runs import run_directory
from tests.backend.test_orchestrator_api import RUN, make_client


def overview(client):
    response = client.get("/api/orchestrator/overview")
    assert response.status_code == 200, response.text
    return response.json()


def run_page(client, query=""):
    response = client.get(f"/api/orchestrator/overview/runs{query}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def world(tmp_path):
    repo, client = make_client(tmp_path)
    with client:
        yield repo, client


def test_the_totals_match_what_the_run_view_shows(world):
    _, client = world
    progress = client.get(f"/api/runs/{RUN}/progress").json()
    out = overview(client)
    assert out["runs"] == {
        "total": 1,
        "by_state": {"finished": 1},
        "stories_approved": 1,
        "stories": 1,
        "stories_complete": 1,
        "stories_active": 0,
    }
    assert out["tasks"]["planned"] == 2 and out["tasks"]["merged"] == 2
    assert out["tasks"]["attempts"] == 2 and out["tasks"]["retries"] == 0
    assert out["cost"]["build"] == pytest.approx(progress["cost"])
    assert out["cost"]["total"] == pytest.approx(out["cost"]["build"] + out["cost"]["planning"])
    assert {g["name"] for g in out["by_role"]} >= {"builder", "reviewer"}


def test_the_run_list_has_one_row_per_run_with_its_story_and_tasks(world):
    _, client = world
    (row,) = run_page(client)["items"]
    assert (row["run_id"], row["story_key"], row["state"]) == (RUN, "SMT-61", "finished")
    assert (row["tasks_merged"], row["tasks_planned"], row["planned_from"]) == (2, 2, "plan")
    assert row["started_at"].endswith("Z") or "+" in row["started_at"]


def test_a_missing_plan_file_falls_back_to_the_database_count(tmp_path):
    repo, client = make_client(tmp_path)
    (run_directory(repo, RUN) / "plan.json").unlink()
    with client:
        (row,) = run_page(client)["items"]
    assert row["planned_from"] == "database" and row["tasks_planned"] == 2


def test_a_project_nobody_built_adds_up_to_zeros(tmp_path):
    _, client = make_client(tmp_path, run=False)
    with client:
        out = overview(client)
        page = run_page(client)
    assert out["runs"]["total"] == 0 and "recent" not in out
    assert page == {"total": 0, "page": 0, "pages": 1, "size": 10, "items": []}
    assert out["cost"]["build"] == 0 and out["tasks"] == {
        "planned": 0,
        "merged": 0,
        "attempts": 0,
        "retries": 0,
    }


def test_a_page_says_where_it_is_among_the_pages(world):
    _, client = world
    page = run_page(client, "?page=0&size=1")
    assert (page["total"], page["page"], page["pages"], page["size"]) == (1, 0, 1, 1)
    assert len(page["items"]) == 1


def test_a_page_past_the_end_is_answered_with_the_last_page(world):
    _, client = world
    page = run_page(client, "?page=7&size=1")
    assert page["page"] == 0 and len(page["items"]) == 1


@pytest.mark.parametrize("query", ["size=0", "size=51", "size=many", "page=-1", "page=x"])
def test_the_page_and_size_must_be_in_range(world, query):
    _, client = world
    assert client.get(f"/api/orchestrator/overview/runs?{query}").status_code == 422
