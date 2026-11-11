import pytest
from fastapi.testclient import TestClient

from backend.main import create_app, load_settings
from core.settings import Settings, get_settings


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path / "data",
        "jira_site_url": "https://x.atlassian.net",
        "jira_email": "a@b.com",
        "jira_api_token": "topsecret",
        "github_token": "ghsecret",
        "repository": "SDJKTECH/Skill-Matrix-Testing",
        "project_path": tmp_path / "sm",
        "base_branch": "development",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as client:
        yield client


def test_startup_creates_the_database_file(client, tmp_path):
    assert (tmp_path / "data" / "brigade.db").is_file()


def test_health_answers_without_secrets(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "project": "Skill-Matrix-Testing",
        "jira_site_url": "https://x.atlassian.net",
        "jira_configured": True,
        "user_initials": "A",
    }
    assert "topsecret" not in response.text and "ghsecret" not in response.text


def test_the_env_project_is_listed(client, tmp_path):
    projects = client.get("/api/projects").json()
    assert len(projects) == 1
    assert projects[0]["name"] == "Skill-Matrix-Testing"
    assert projects[0]["repository"] == "SDJKTECH/Skill-Matrix-Testing"
    assert projects[0]["local_path"] == str(tmp_path / "sm")
    assert projects[0]["base_branch"] == "development"


def test_starting_twice_does_not_duplicate_and_picks_up_changes(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))):
        pass
    with TestClient(create_app(make_settings(tmp_path, base_branch="main"))) as client:
        projects = client.get("/api/projects").json()
    assert len(projects) == 1
    assert projects[0]["base_branch"] == "main"


def test_local_only_project_is_named_after_its_folder(tmp_path):
    settings = make_settings(tmp_path, repository="", project_path=tmp_path / "payments-api")
    with TestClient(create_app(settings)) as client:
        projects = client.get("/api/projects").json()
    assert [p["name"] for p in projects] == ["payments-api"]
    assert projects[0]["repository"] is None


def test_no_project_in_env_means_an_empty_list(tmp_path):
    settings = make_settings(tmp_path, repository="", project_path=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/projects").json() == []
        assert client.get("/api/health").json()["project"] is None


def test_the_page_and_its_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    for text in ("Publisher", "Planning", "Orchestrator", "Chat ID", "Message Publisher"):
        assert text in page.text
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/css/app.css").status_code == 200
    assert client.get("/assets/logo.png").status_code == 200


SCRIPTS = [
    "js/components/markdown.js",
    "js/components/plan-tree.js",
    "js/tabs/publisher.js",
    "js/app.js",
]


def test_the_publisher_scripts_load_in_order_as_javascript(client):
    page = client.get("/").text
    positions = [page.index(f'<script src="{script}">') for script in SCRIPTS]
    assert positions == sorted(positions)  # helpers before the tab, the tab before app.js
    for script in SCRIPTS:
        response = client.get("/" + script)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript")


def test_the_publisher_tab_has_its_controls(client):
    page = client.get("/").text
    for element_id in ("message", "file-input", "attach", "send", "chat-list", "new-chat"):
        assert f'id="{element_id}"' in page
    assert 'accept=".txt,.md,.docx,.pdf"' in page


def test_unknown_api_path_is_not_the_page(client):
    assert client.get("/api/nope").status_code == 404


def test_a_bad_setting_stops_startup_and_names_it(monkeypatch):
    monkeypatch.setenv("BRIGADE_MAX_RETRIES", "9")
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit) as stopped:
            load_settings()
    finally:
        get_settings.cache_clear()
    assert "BRIGADE_MAX_RETRIES" in str(stopped.value)
