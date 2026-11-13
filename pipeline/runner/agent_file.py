"""An agent definition (.claude/agents/<name>.md) as the JSON Claude Code's --agents flag takes.

Claude Code finds agent files under the folder it is started in. An agent that works inside a
project's worktree (the Builder) is started in that folder, where Brigade's own agent files are
not, so the definition is passed as a file instead.
"""

from pathlib import Path
from typing import Any


class AgentFileError(ValueError):
    """The agent file is missing or does not have a header and a body."""


def split_agent_file(text: str) -> tuple[dict[str, str], str]:
    """The simple ``key: value`` header lines and the body of an agent .md file."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise AgentFileError("the agent file must start with a --- header")
    try:
        end = [line.strip() for line in lines].index("---", 1)
    except ValueError:
        raise AgentFileError("the agent file's header has no closing ---") from None
    header = {}
    for line in lines[1:end]:
        key, colon, value = line.partition(":")
        if colon and key.strip():
            header[key.strip()] = value.strip()
    return header, "\n".join(lines[end + 1 :]).strip()


def agent_definitions(name: str, path: Path) -> dict[str, Any]:
    """``{name: {description, prompt}}`` from the agent file at `path`."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise AgentFileError(f"the agent file {path} could not be read: {exc}") from None
    header, body = split_agent_file(text)
    if not body:
        raise AgentFileError(f"the agent file {Path(path).name} has no instructions")
    return {name: {"description": header.get("description") or name, "prompt": body}}
