"""The only place that reads .env and the environment.

Everything else asks get_settings(). For now .env also names the one project Brigade works on;
to work on another project, change those values. Later they move to the projects table.
"""

import re
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
    # Optional. Empty = name the project from the repository, else from its folder.
    project_name: str = Field("", validation_alias="BRIGADE_PROJECT_NAME")
    # The project's docs folder, relative to its root (e.g. docs). Empty = it has none.
    docs_dir: str = Field("docs", validation_alias="BRIGADE_DOCS_DIR")
    # How the project's tests run, from its root. Empty = python -m pytest -q.
    # A leading `python` means the project's own .venv Python when it has one.
    test_command: str = Field("", validation_alias="BRIGADE_TEST_COMMAND")

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

    @field_validator("docs_dir")
    @classmethod
    def _relative_folder(cls, value: str) -> str:
        folder = value.strip().replace("\\", "/").strip("/")
        parts = folder.split("/") if folder else []
        if folder.startswith("~") or ":" in folder or ".." in parts:
            raise ValueError("must be a folder inside the project, such as docs")
        return folder

    @field_validator("jira_project_key")
    @classmethod
    def _upper_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("data_dir", "worktree_root", "project_path", mode="before")
    @classmethod
    def _reject_escape_characters(cls, value: object) -> object:
        # "C:\Users\anjishnu" in double quotes turns \a into a hidden control character.
        if isinstance(value, str) and any(ord(char) < 32 for char in value):
            raise ValueError(
                "the path contains a hidden control character, usually from a backslash escape "
                "such as \\a or \\t. In .env write Windows paths without quotes, in single quotes, "
                "or with forward slashes"
            )
        return value

    @field_validator("data_dir", "worktree_root", "project_path")
    @classmethod
    def _expand(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

    @property
    def resolved_project_name(self) -> str:
        """Name shown in the project selector: explicit name, repository, folder, Jira key."""
        if self.project_name.strip():
            return self.project_name.strip()
        if self.repository.strip():
            return self.repository.strip().rstrip("/").split("/")[-1]
        if self.project_path is not None and self.project_path.name:
            return self.project_path.name
        return self.jira_project_key

    @property
    def user_initials(self) -> str:
        """Two letters for the avatar, from the Jira email (anjishnu.kumbhakar@x -> AK)."""
        parts = [p for p in re.split(r"[._\-+]", self.jira_email.split("@")[0]) if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

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
    return Settings()  # type: ignore[call-arg]  # BaseSettings loads omitted fields from env/defaults.
