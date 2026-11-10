"""The only place that reads .env and the environment.

Everything else asks get_settings(). For now .env also names the one project Brigade works on;
to work on another project, change those values. Later they move to the projects table.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATA_DIR = Path.home() / ".agent-brigade"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"  # the repo folder, wherever you start from


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # "KEY=" in .env means "not set", so the default applies
        extra="ignore",
        populate_by_name=True,
    )

    # Credentials
    jira_email: str = Field("", validation_alias="JIRA_EMAIL")
    jira_api_token: SecretStr = Field(SecretStr(""), validation_alias="JIRA_API_TOKEN")
    github_token: SecretStr = Field(SecretStr(""), validation_alias="BRIGADE_GITHUB_TOKEN")

    # Jira site
    jira_site_url: str = Field("", validation_alias="JIRA_SITE_URL")

    # The project Brigade works on (change these to switch project)
    tracker: Literal["jira", "github"] = Field("jira", validation_alias="BRIGADE_TRACKER")
    jira_project_key: str = Field("", validation_alias="JIRA_PROJECT_KEY")
    repository: str = Field("", validation_alias="BRIGADE_REPOSITORY")  # owner/name
    project_path: Path | None = Field(None, validation_alias="BRIGADE_PROJECT_PATH")
    base_branch: str = Field("main", validation_alias="BRIGADE_BASE_BRANCH")

    # Where things live
    data_dir: Path = Field(DEFAULT_DATA_DIR, validation_alias="BRIGADE_DATA_DIR")
    worktree_root: Path | None = Field(None, validation_alias="BRIGADE_WORKTREE_ROOT")

    # Limits
    max_retries: int = Field(2, ge=0, le=5, validation_alias="BRIGADE_MAX_RETRIES")
    max_parallel: int = Field(3, ge=1, le=8, validation_alias="BRIGADE_MAX_PARALLEL")
    test_timeout: int = Field(1200, ge=60, le=86400, validation_alias="BRIGADE_TEST_TIMEOUT")

    @field_validator("jira_site_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.strip().rstrip("/")

    @field_validator("jira_project_key")
    @classmethod
    def _upper_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("data_dir", "worktree_root", "project_path")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    @property
    def db_path(self) -> Path:
        return self.data_dir / "brigade.db"

    @property
    def worktrees_dir(self) -> Path:
        return self.worktree_root or self.data_dir / "worktrees"

    @property
    def jira_configured(self) -> bool:
        return bool(
            self.jira_site_url and self.jira_email and self.jira_api_token.get_secret_value()
        )

    def ensure_dirs(self) -> None:
        """Create the data and worktree folders. Call once at start-up, not at import."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
