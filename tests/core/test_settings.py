from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from core.settings import Settings

ENV_NAMES = [
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "BRIGADE_GITHUB_TOKEN",
    "JIRA_SITE_URL",
    "JIRA_PROJECT_KEY",
    "BRIGADE_DATA_DIR",
    "BRIGADE_WORKTREE_ROOT",
    "BRIGADE_TRACKER",
    "BRIGADE_REPOSITORY",
    "BRIGADE_PROJECT_PATH",
    "BRIGADE_BASE_BRANCH",
    "BRIGADE_PROJECT_NAME",
    "BRIGADE_MAX_RETRIES",
    "BRIGADE_MAX_PARALLEL",
    "BRIGADE_TEST_TIMEOUT",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def load(tmp_path: Path, text: str = "") -> Settings:
    env_file = tmp_path / ".env"
    env_file.write_text(text, encoding="utf-8")
    return cast(Any, Settings)(_env_file=env_file)


def test_defaults_when_nothing_is_set(tmp_path):
    s = load(tmp_path)
    assert (s.max_retries, s.max_parallel, s.test_timeout) == (2, 3, 1200)
    assert s.data_dir == Path.home() / ".agent-brigade"
    assert s.db_path == s.data_dir / "brigade.db"
    assert s.worktrees_dir == s.data_dir / "worktrees"
    assert not s.jira_configured


def test_empty_values_in_env_file_mean_not_set(tmp_path):
    s = load(tmp_path, "BRIGADE_DATA_DIR=\nBRIGADE_MAX_RETRIES=\nJIRA_EMAIL=\n")
    assert s.data_dir == Path.home() / ".agent-brigade"
    assert s.max_retries == 2


def test_values_are_read_and_cleaned(tmp_path):
    s = load(
        tmp_path,
        "JIRA_SITE_URL=https://x.atlassian.net/\n"
        "JIRA_EMAIL=a@b.com\nJIRA_API_TOKEN=secret\n"
        "JIRA_PROJECT_KEY=ab\nBRIGADE_MAX_PARALLEL=5\n"
        f"BRIGADE_DATA_DIR={tmp_path / 'data'}\n",
    )
    assert s.jira_site_url == "https://x.atlassian.net"
    assert s.jira_project_key == "AB"
    assert s.max_parallel == 5
    assert s.data_dir == tmp_path / "data"
    assert s.jira_configured


def test_token_never_shows_in_repr(tmp_path):
    s = load(tmp_path, "JIRA_API_TOKEN=topsecret\nBRIGADE_GITHUB_TOKEN=ghsecret\n")
    assert "topsecret" not in repr(s)
    assert "ghsecret" not in repr(s)
    assert s.jira_api_token.get_secret_value() == "topsecret"


def test_real_environment_beats_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BRIGADE_MAX_RETRIES", "4")
    s = load(tmp_path, "BRIGADE_MAX_RETRIES=1\n")
    assert s.max_retries == 4


@pytest.mark.parametrize(
    "line", ["BRIGADE_MAX_RETRIES=9", "BRIGADE_MAX_PARALLEL=0", "BRIGADE_TEST_TIMEOUT=5"]
)
def test_out_of_range_limits_are_rejected(tmp_path, line):
    with pytest.raises(ValidationError):
        load(tmp_path, line + "\n")


def test_ensure_dirs_creates_folders(tmp_path):
    s = load(tmp_path, f"BRIGADE_DATA_DIR={tmp_path / 'data'}\n")
    s.ensure_dirs()
    assert (tmp_path / "data").is_dir()
    assert (tmp_path / "data" / "worktrees").is_dir()


def test_project_values_come_from_env(tmp_path):
    s = load(
        tmp_path,
        "JIRA_PROJECT_KEY=sm\nBRIGADE_REPOSITORY=SDJKTECH/Skill-Matrix-Testing\n"
        f"BRIGADE_PROJECT_PATH={tmp_path / 'sm'}\nBRIGADE_BASE_BRANCH=development\n",
    )
    assert s.tracker == "jira"
    assert s.jira_project_key == "SM"
    assert s.repository == "SDJKTECH/Skill-Matrix-Testing"
    assert s.project_path == tmp_path / "sm"
    assert s.base_branch == "development"


def test_project_defaults(tmp_path):
    s = load(tmp_path)
    assert (s.tracker, s.repository, s.project_path, s.base_branch) == ("jira", "", None, "main")


def test_unknown_tracker_is_rejected(tmp_path):
    with pytest.raises(ValidationError):
        load(tmp_path, "BRIGADE_TRACKER=trello\n")


def test_env_file_is_in_the_repo_folder():
    from core.settings import ENV_FILE

    assert ENV_FILE.parent == Path(__file__).resolve().parents[2]


def test_project_name_comes_from_name_then_repository_then_folder_then_key(tmp_path):
    folder = f"BRIGADE_PROJECT_PATH={tmp_path / 'payments-api'}\n"
    repo = "BRIGADE_REPOSITORY=SDJKTECH/Skill-Matrix-Testing\n"
    assert (
        load(tmp_path, "BRIGADE_PROJECT_NAME=Mine\n" + repo + folder).resolved_project_name
        == "Mine"
    )
    assert load(tmp_path, repo + folder).resolved_project_name == "Skill-Matrix-Testing"
    assert load(tmp_path, folder).resolved_project_name == "payments-api"
    assert load(tmp_path, "JIRA_PROJECT_KEY=sm\n").resolved_project_name == "SM"
    assert load(tmp_path).resolved_project_name == ""


def test_a_path_with_a_hidden_escape_character_is_rejected(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('BRIGADE_PROJECT_PATH="C:\\Users\\anjishnu\\x"\n', encoding="utf-8")
    with pytest.raises(ValidationError) as error:
        cast(Any, Settings)(_env_file=env_file)
    assert "BRIGADE_PROJECT_PATH" in str(error.value)
    assert "control character" in str(error.value)


def test_single_quoted_and_unquoted_windows_paths_are_kept_as_written(tmp_path):
    for text in ("'C:\\Users\\anjishnu\\x'", "C:\\Users\\anjishnu\\x"):
        s = load(tmp_path, f"BRIGADE_PROJECT_PATH={text}\n")
        assert "anjishnu" in str(s.project_path) and "\x07" not in str(s.project_path)


@pytest.mark.parametrize(
    ("email", "initials"),
    [("anjishnu.kumbhakar@jktech.com", "AK"), ("a@b.com", "A"), ("", "?")],
)
def test_user_initials(tmp_path, email, initials):
    assert load(tmp_path, f"JIRA_EMAIL={email}\n").user_initials == initials
