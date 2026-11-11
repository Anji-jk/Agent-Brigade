import json

import pytest
from pydantic import SecretStr

from core.settings import Settings
from pipeline.publisher import chat as chat_module
from pipeline.publisher.chat import ChatError, PublisherChat
from pipeline.publisher.guard import ALLOWED_COMMANDS
from pipeline.runner.claude_runner import AgentError, AgentReply
from tests.doubles.jira import SITE, FakeJira

SESSION = "11111111-2222-3333-4444-555555555555"
CRITERIA = "Acceptance criteria:\n- done"


def plan_reply(summary="Certificate expiry reminder", description=CRITERIA):
    block = {
        "stories": [
            {
                "epic": "SMT-2",
                "summary": summary,
                "description": description,
                "subtasks": [{"summary": "API", "description": CRITERIA}],
            }
        ]
    }
    return f"Story: {summary}\n  Sub-task: API\n\n```plan\n{json.dumps(block)}\n```"


class FakeRunner:
    """Answers each agent run with the next scripted reply (text, or an exception)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return AgentReply(text=answer, session_id=request.session_id, cost_usd=0.01)


@pytest.fixture
def jira():
    return FakeJira().add("SMT-2", "epic", "Employee Profile")


def make_chat(jira, runner):
    settings = Settings.model_construct(
        jira_site_url=SITE,
        jira_email="a@b.c",
        jira_api_token=SecretStr("t"),
        jira_project_key="SMT",
    )
    return PublisherChat(settings, runner, jira.client, new_session_id=lambda: SESSION)


def test_a_new_chat_starts_a_claude_session(jira):
    runner = FakeRunner("Which epic should this go under?")
    turn = make_chat(jira, runner).send("  Remind people before certificates expire  ")

    request = runner.requests[0]
    assert request.agent == "publisher" and request.resume is False
    assert request.session_id == SESSION and request.allowed_bash == ALLOWED_COMMANDS
    assert request.prompt == "Remind people before certificates expire"
    assert request.cwd == chat_module.REPO_ROOT
    assert turn.session_id == SESSION and turn.reply == "Which epic should this go under?"
    assert turn.plan is None and turn.problems == ()


def test_a_later_message_resumes_the_given_session(jira):
    runner = FakeRunner("Second answer")
    turn = make_chat(jira, runner).send("More detail", "aaaa-bbbb")
    assert runner.requests[0].resume is True and runner.requests[0].session_id == "aaaa-bbbb"
    assert turn.session_id == "aaaa-bbbb"


def test_a_checked_plan_is_returned_without_its_block(jira):
    turn = make_chat(jira, FakeRunner(plan_reply())).send("Add a reminder")
    assert "```plan" not in turn.reply and turn.reply.startswith("Story: Certificate")
    assert turn.plan is not None
    assert turn.plan.counts() == {"stories": 1, "subtasks": 1}
    assert turn.plan.stories[0].summary == "Certificate expiry reminder"


def test_a_refused_plan_is_sent_back_once_for_fixing(jira):
    runner = FakeRunner(plan_reply(description="no criteria"), plan_reply())
    turn = make_chat(jira, runner).send("Add a reminder")

    fix = runner.requests[1]
    assert fix.resume is True and fix.session_id == SESSION
    assert "not from the user" in fix.prompt and "Acceptance criteria:" in fix.prompt
    assert turn.plan is not None and turn.problems == ()
    assert turn.cost_usd == pytest.approx(0.02)


def test_a_plan_still_wrong_after_the_fix_is_returned_with_its_problems(jira):
    bad = plan_reply(description="no criteria")
    runner = FakeRunner(bad, bad)
    turn = make_chat(jira, runner).send("Add a reminder")
    assert len(runner.requests) == 1 + chat_module.FIX_ROUNDS
    assert turn.plan is None
    assert any("Acceptance criteria" in p for p in turn.problems)


def test_a_fix_reply_without_a_plan_block_is_reported(jira):
    runner = FakeRunner(plan_reply(description="no criteria"), "Sorry, which epic?")
    turn = make_chat(jira, runner).send("Add a reminder")
    assert turn.plan is None and turn.problems == ("The corrected reply has no plan block.",)


def test_a_plan_for_an_epic_that_does_not_exist_is_refused(jira):
    wrong = plan_reply().replace("SMT-2", "SMT-99")
    turn = make_chat(jira, FakeRunner(wrong, wrong)).send("Add a reminder")
    assert turn.plan is None and turn.problems == ("Epic SMT-99 does not exist in space SMT.",)


def test_jira_down_is_not_sent_to_the_agent_to_fix(jira):
    jira.down = True
    runner = FakeRunner(plan_reply())
    turn = make_chat(jira, runner).send("Add a reminder")
    assert len(runner.requests) == 1
    assert turn.problems[0].startswith("Jira could not be checked")


def test_a_failed_run_is_raised(jira):
    with pytest.raises(AgentError, match="not logged in"):
        make_chat(jira, FakeRunner(AgentError("not logged in"))).send("Hello")


@pytest.mark.parametrize("message", ["", "   ", "x" * (chat_module.MAX_MESSAGE_CHARS + 1)])
def test_empty_or_huge_messages_are_refused(jira, message):
    runner = FakeRunner()
    with pytest.raises(ChatError):
        make_chat(jira, runner).send(message)
    assert runner.requests == []
