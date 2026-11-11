"""One Publisher turn: ask the agent, check its plan. No database here.

    python -m pipeline.publisher.chat "Employees get a reminder before a certificate expires"
    python -m pipeline.publisher.chat --session <session id> "Make it one story"

A chat is one Claude session: the first message starts it, every later message continues it with
--resume. The reply may end with a plan block; it is taken out and checked by the guard, and the
caller gets either a checked plan or the problems found. Saving chats and proposals, and creating
the plan in Jira after Confirm, belong to the backend service (step 2.7).
"""

import argparse
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.settings import Settings, get_settings
from core.trackers.errors import TrackerError
from core.trackers.jira.client import JiraClient
from pipeline.publisher.guard import (
    ALLOWED_COMMANDS,
    Plan,
    PlanCheck,
    check_plan,
    find_plan_block,
    without_plan_block,
)
from pipeline.runner.claude_runner import (
    AgentError,
    AgentReply,
    AgentRequest,
    AgentRunner,
    ClaudeCliRunner,
)

REPO_ROOT = Path(__file__).resolve().parents[2]  # the Agent-Brigade folder
AGENT = "publisher"
FIX_ROUNDS = 1  # times the agent is asked to correct a plan the guard refused
MAX_MESSAGE_CHARS = 200_000
SYSTEM_MARKER = "[Message from the Brigade system, not from the user]"  # hidden in previous chats


class ChatError(Exception):
    """The message cannot be sent (empty, too long, settings missing)."""


def fix_prompt(problems: tuple[str, ...]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        f"{SYSTEM_MARKER}\n"
        "The plan block of your last proposal was checked and cannot be confirmed:\n"
        f"{listed}\n"
        "Fix these points and send the whole proposal again with a new plan block. "
        "Keep everything else as it was. If a point cannot be fixed without the user, "
        "ask the user instead."
    )


@dataclass(frozen=True)
class Turn:
    session_id: str  # Claude's session id: its transcript is <session_id>.jsonl
    reply: str  # the agent's answer without the plan block
    plan: Plan | None  # the checked plan, ready for Confirm
    problems: tuple[str, ...]  # why the plan in the reply was not accepted
    cost_usd: float | None


class PublisherChat:
    def __init__(
        self,
        settings: Settings,
        runner: AgentRunner,
        client_factory: Callable[[Settings], JiraClient] = JiraClient.from_settings,
        repo_root: Path = REPO_ROOT,
        new_session_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._client_factory = client_factory
        self._repo_root = repo_root
        self._new_session_id = new_session_id

    def send(self, message: str, session_id: str | None = None) -> Turn:
        """Send a message. No session id starts a new chat; a session id continues that one."""
        message = message.strip()
        if not message:
            raise ChatError("The message is empty.")
        if len(message) > MAX_MESSAGE_CHARS:
            raise ChatError(f"The message is longer than {MAX_MESSAGE_CHARS} characters.")
        space = self._settings.jira_project_key
        if not space:
            raise ChatError("JIRA_PROJECT_KEY is empty in .env.")

        resume = session_id is not None
        reply = self._ask(message, session_id or self._new_session_id(), resume)
        cost = reply.cost_usd
        check: PlanCheck | None = None
        block = find_plan_block(reply.text)
        if block is not None:
            check = self._check(block, space)
            for _ in range(FIX_ROUNDS):
                if check.ok or not check.fixable:
                    break
                reply = self._ask(fix_prompt(check.problems), reply.session_id, True)
                cost = _add(cost, reply.cost_usd)
                block = find_plan_block(reply.text)
                if block is None:
                    check = PlanCheck(None, ("The corrected reply has no plan block.",))
                    break
                check = self._check(block, space)

        return Turn(
            session_id=reply.session_id,
            reply=without_plan_block(reply.text),
            plan=check.plan if check and check.ok else None,
            problems=check.problems if check else (),
            cost_usd=cost,
        )

    def _ask(self, prompt: str, session_id: str, resume: bool) -> AgentReply:
        return self._runner.run(
            AgentRequest(
                agent=AGENT,
                prompt=prompt,
                cwd=self._repo_root,
                session_id=session_id,
                resume=resume,
                allowed_bash=ALLOWED_COMMANDS,
            )
        )

    def _check(self, block: str, space: str) -> PlanCheck:
        try:
            client = self._client_factory(self._settings)
        except TrackerError as exc:
            return PlanCheck(None, (f"Jira could not be checked: {exc}",), fixable=False)
        try:
            return check_plan(block, client, space)
        finally:
            client.close()


def _add(a: float | None, b: float | None) -> float | None:
    return None if a is None and b is None else (a or 0.0) + (b or 0.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.publisher.chat")
    parser.add_argument("message")
    parser.add_argument("--session", help="continue the chat with this Claude session id")
    args = parser.parse_args(argv)

    chat = PublisherChat(get_settings(), ClaudeCliRunner())
    try:
        turn = chat.send(args.message, args.session)
    except (ChatError, AgentError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Session {turn.session_id}\n")
    print(turn.reply, "\n")
    if turn.plan:
        for story in turn.plan.stories:  # the agent no longer lists them: the page draws them
            print(f"Story under {story.epic}: {story.summary}")
            for subtask in story.subtasks:
                print(f"  Sub-task: {subtask.summary}")
        counts = turn.plan.counts()
        print(
            f"Plan checked: {counts['stories']} stories, {counts['subtasks']} sub-tasks. "
            "Ready for Confirm."
        )
    elif turn.problems:
        print("Plan not accepted:")
        print("\n".join(f"- {p}" for p in turn.problems))
    else:
        print("No plan in this reply.")
    if turn.cost_usd is not None:
        print(f"Cost: ${turn.cost_usd:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
