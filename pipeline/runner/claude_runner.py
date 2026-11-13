"""The agent runner (technical document 7.1): the one place that knows how an agent is started.

Today that is Claude Code's command line, `claude -p`, with the agent definition from
.claude/agents/<name>.md. Everything else (the Publisher chat, later the pipeline stages) talks to
the small AgentRunner interface below, so another way of running agents (the Claude Agent SDK,
Strands, a hosted runner) can replace ClaudeCliRunner without changes elsewhere.

How an agent is restricted, when started by ClaudeCliRunner:
- --tools: the only built-in tools it has (Bash for the Publisher; Read, Grep and Glob for the
  Planner; never Edit, Write or web unless a request names them);
- a settings file with permissions.allow listing the exact commands it may run, and
  --permission-mode dontAsk, so anything not listed is refused instead of asked about;
- permissions.deny in the same file: files it may never read, such as every .env;
- --max-turns and --max-budget-usd: how many steps and how many dollars one run may use;
- --add-dir: folders besides the Agent-Brigade folder it may read (the project being planned);
- --setting-sources project: your personal Claude Code settings (which may allow more) are
  not loaded; --strict-mcp-config: no MCP servers.
"""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Protocol

from pipeline.runner.agent_file import AgentFileError, agent_definitions

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
    tools: tuple[str, ...] = ("Bash",)  # the built-in tools it has, nothing else
    add_dirs: tuple[Path, ...] = ()  # folders besides cwd it may read
    deny: tuple[str, ...] = ()  # permission rules it may never use, e.g. "Read(//c/x/.env)"
    permission_mode: str = "dontAsk"  # "acceptEdits": edits inside cwd pass, the rest is denied
    max_turns: int | None = None  # None: Claude Code's own limit
    max_budget_usd: float | None = None  # None: no spending cap for this run
    model: str | None = None  # a model alias; None: the agent file's own model
    effort: str | None = None  # low | medium | high | xhigh | max; None: the agent's own
    agent_file: Path | None = None  # an agent definition outside cwd, such as Brigade's builder.md


@dataclass(frozen=True)
class AgentReply:
    text: str
    session_id: str
    cost_usd: float | None = None
    turns: int | None = None
    duration_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_tokens: int | None = None
    model_used: str | None = None


class AgentRunner(Protocol):
    def run(self, request: AgentRequest) -> AgentReply: ...


def claude_settings(
    allowed_bash: tuple[str, ...],
    deny: tuple[str, ...] = (),
    shells: tuple[str, ...] = ("Bash",),
) -> dict[str, Any]:
    """The Claude Code settings for one run: only these command lines, and never `deny`.

    On Windows without Git Bash Claude Code has no Bash tool and runs commands with PowerShell,
    so a command line is allowed under each shell tool the agent was given (`shells`). Edit
    and Write are not allowed by rule: on Windows such an allow rule is ignored (a Claude Code
    bug), so an agent that edits runs in acceptEdits mode instead, see claude_command.
    """
    permissions: dict[str, Any] = {
        "allow": [f"{shell}({command})" for command in allowed_bash for shell in shells],
        "defaultMode": "dontAsk",
    }
    if deny:
        permissions["deny"] = list(deny)
    return {"permissions": permissions}


def path_rule(tool: str, folder: PurePath, pattern: str) -> str:
    """A permission rule for `pattern` under an absolute `folder`, e.g. Read(//c/proj/**/.env).

    Claude Code writes an absolute path with two leading slashes, and on Windows matches
    paths in POSIX form with the drive as a lower-case folder: C:\\Users becomes /c/Users.
    """
    posix = folder.as_posix()
    if folder.drive:
        posix = "/" + folder.drive[0].lower() + posix[len(folder.drive) :]
    return f"{tool}(/{posix.rstrip('/')}/{pattern})"


def secret_rules(*folders: PurePath) -> tuple[str, ...]:
    """Deny rules that keep every .env file in these folders, at any depth, unread."""
    return tuple(
        path_rule("Read", folder, pattern)
        for folder in folders
        for pattern in ("**/.env", "**/.env.*")
    )


def claude_command(
    executable: str, request: AgentRequest, settings_file: Path, agents_file: Path | None = None
) -> list[str]:
    command = [
        executable,
        "-p",  # the prompt comes on stdin: no length limit, no shell quoting
        "--agent",
        request.agent,
        "--output-format",
        "json",
        "--tools",
        ",".join(request.tools),
        "--permission-mode",
        request.permission_mode,
        "--setting-sources",
        "project",
        "--settings",
        str(settings_file),
        "--strict-mcp-config",
    ]
    if request.permission_mode != "dontAsk":  # nobody can answer a prompt: deny what would ask
        command += ["--permission-prompts", "none"]
    if agents_file is not None:  # the definition is not under cwd: hand it over as a file
        command += ["--agents", str(agents_file)]
    if request.model:
        command += ["--model", request.model]
    if request.effort:
        command += ["--effort", request.effort]
    for folder in request.add_dirs:
        command += ["--add-dir", str(folder)]
    if request.max_turns is not None:
        command += ["--max-turns", str(request.max_turns)]
    if request.max_budget_usd is not None:
        command += ["--max-budget-usd", f"{request.max_budget_usd:.4f}"]
    if request.resume:
        return [*command, "--resume", request.session_id]
    return [*command, "--session-id", request.session_id]


def stop_reason(result: dict[str, Any], request: AgentRequest) -> str:
    """Why the agent stopped, in words; a limit it hit says which one and how big it was."""
    subtype = result.get("subtype")
    if subtype == "error_max_turns" and request.max_turns:
        return f"it reached its limit of {request.max_turns} turns ({subtype})"
    if subtype == "error_max_budget_usd" and request.max_budget_usd:
        return f"it reached its spending limit of ${request.max_budget_usd:.2f} ({subtype})"
    return str(result.get("result") or subtype or "unknown error")


def _table(value: Any) -> dict[str, Any]:
    """`value` if it is a JSON object, else an empty one, so every .get() below is safe."""
    return value if isinstance(value, dict) else {}


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
        reason = stop_reason(result, request)
        raise AgentError(f"The {request.agent} agent stopped: {reason[:MAX_ERROR_CHARS]}")
    usage = _table(result.get("usage"))
    models = _table(result.get("modelUsage"))
    cached = [usage.get("cache_read_input_tokens"), usage.get("cache_creation_input_tokens")]
    return AgentReply(
        text=str(result.get("result") or ""),
        session_id=str(result.get("session_id") or request.session_id),
        cost_usd=result.get("total_cost_usd"),
        turns=result.get("num_turns"),
        duration_ms=result.get("duration_ms"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cache_tokens=sum(n for n in cached if isinstance(n, int)) if any(cached) else None,
        model_used=", ".join(models) or None,
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
            settings = claude_settings(
                request.allowed_bash,
                request.deny,
                tuple(tool for tool in ("Bash", "PowerShell") if tool in request.tools),
            )
            settings_file.write_text(json.dumps(settings), "utf-8")
            agents_file = None
            if request.agent_file is not None:
                agents_file = Path(folder) / "agents.json"
                try:
                    definitions = agent_definitions(request.agent, request.agent_file)
                except AgentFileError as exc:
                    raise AgentError(str(exc)) from None
                agents_file.write_text(json.dumps(definitions), "utf-8")
            try:
                # Bytes, not text mode: text mode on Windows turns every \n of the prompt into
                # \r\n, which Claude Code then stores in the transcript.
                done = self._run(
                    claude_command(executable, request, settings_file, agents_file),
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


def agent_header(cwd: Path, agent: str) -> dict[str, str]:
    """The simple `key: value` lines of .claude/agents/<agent>.md's header, such as its model."""
    text = (Path(cwd) / ".claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---" or "---" not in [x.strip() for x in lines[1:]]:
        return {}
    end = [x.strip() for x in lines].index("---", 1)
    header = {}
    for line in lines[1:end]:
        key, colon, value = line.partition(":")
        if colon and key.strip():
            header[key.strip()] = value.strip()
    return header
