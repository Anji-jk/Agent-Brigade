"""The agent runner (technical document 7.1): the one place that knows how an agent is started.

Today that is Claude Code's command line, `claude -p`, with the agent definition from
.claude/agents/<name>.md. Everything else (the Publisher chat, later the pipeline stages) talks to
the small AgentRunner interface below, so another way of running agents (the Claude Agent SDK,
Strands, a hosted runner) can replace ClaudeCliRunner without changes elsewhere.

How an agent is restricted, when started by ClaudeCliRunner:
- --tools Bash: Bash is the only built-in tool it has (no Read, Edit, Write, web);
- a settings file with permissions.allow listing the exact commands it may run, and
  --permission-mode dontAsk, so anything not listed is refused instead of asked about;
- --setting-sources project: your personal Claude Code settings (which may allow more) are
  not loaded; --strict-mcp-config: no MCP servers.
"""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

DEFAULT_TIMEOUT_SECONDS = 600.0
MAX_ERROR_CHARS = 500


class AgentError(Exception):
    """The agent could not be run, or stopped without a usable answer."""


@dataclass(frozen=True)
class AgentRequest:
    agent: str  # the name in .claude/agents/<agent>.md
    prompt: str
    cwd: Path  # always the Agent-Brigade folder: agent files and transcripts are found from it
    session_id: str  # Claude's session id (a UUID)
    resume: bool  # True: continue that session; False: start a new one with this id
    allowed_bash: tuple[str, ...] = ()  # e.g. "python -m pipeline.publisher.cli epics"
    timeout: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class AgentReply:
    text: str
    session_id: str
    cost_usd: float | None = None
    turns: int | None = None
    duration_ms: int | None = None


class AgentRunner(Protocol):
    def run(self, request: AgentRequest) -> AgentReply: ...


def claude_settings(allowed_bash: tuple[str, ...]) -> dict[str, Any]:
    """The Claude Code settings for one run: only these Bash commands, nothing else."""
    return {
        "permissions": {
            "allow": [f"Bash({command})" for command in allowed_bash],
            "defaultMode": "dontAsk",
        }
    }


def claude_command(executable: str, request: AgentRequest, settings_file: Path) -> list[str]:
    command = [
        executable,
        "-p",  # the prompt comes on stdin: no length limit, no shell quoting
        "--agent",
        request.agent,
        "--output-format",
        "json",
        "--tools",
        "Bash",
        "--permission-mode",
        "dontAsk",
        "--setting-sources",
        "project",
        "--settings",
        str(settings_file),
        "--strict-mcp-config",
    ]
    if request.resume:
        return [*command, "--resume", request.session_id]
    return [*command, "--session-id", request.session_id]


def parse_reply(stdout: str, stderr: str, returncode: int, request: AgentRequest) -> AgentReply:
    """The agent's final answer from `claude -p --output-format json`."""
    try:
        result = json.loads(stdout)
    except ValueError:
        detail = (stderr or stdout).strip()[-MAX_ERROR_CHARS:] or "no output"
        raise AgentError(f"Claude Code exited with code {returncode}: {detail}") from None
    if not isinstance(result, dict):
        raise AgentError("Claude Code returned an unexpected answer.")
    if result.get("is_error") or result.get("subtype") not in (None, "success"):
        reason = str(result.get("result") or result.get("subtype") or "unknown error")
        raise AgentError(f"The {request.agent} agent stopped: {reason[:MAX_ERROR_CHARS]}")
    return AgentReply(
        text=str(result.get("result") or ""),
        session_id=str(result.get("session_id") or request.session_id),
        cost_usd=result.get("total_cost_usd"),
        turns=result.get("num_turns"),
        duration_ms=result.get("duration_ms"),
    )


def _text(output: bytes | str | None) -> str:
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output or ""


class ClaudeCliRunner:
    """Runs an agent with the `claude` command. Tests pass a fake `run` instead of subprocess."""

    def __init__(
        self,
        executable: str | None = None,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self._executable = executable
        self._run = run

    def run(self, request: AgentRequest) -> AgentReply:
        executable = self._executable or shutil.which("claude")
        if not executable:
            raise AgentError(
                "Claude Code was not found. Install it, then check that `claude --version` "
                "works in the terminal that starts Brigade."
            )
        with tempfile.TemporaryDirectory(prefix="brigade-agent-") as folder:
            settings_file = Path(folder) / "settings.json"
            settings_file.write_text(json.dumps(claude_settings(request.allowed_bash)), "utf-8")
            try:
                # Bytes, not text mode: text mode on Windows turns every \n of the prompt into
                # \r\n, which Claude Code then stores in the transcript.
                done = self._run(
                    claude_command(executable, request, settings_file),
                    input=request.prompt.encode("utf-8"),
                    capture_output=True,
                    cwd=request.cwd,
                    timeout=request.timeout,
                )
            except subprocess.TimeoutExpired:
                seconds = f"{request.timeout:.0f}"
                raise AgentError(
                    f"The {request.agent} agent did not finish within {seconds} seconds."
                ) from None
            except OSError as exc:
                raise AgentError(f"Claude Code could not be started: {exc}") from exc
        return parse_reply(_text(done.stdout), _text(done.stderr), done.returncode, request)
