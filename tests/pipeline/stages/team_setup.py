"""A prepared project with a test folder, and a fake Claude that plays all three agents."""

import json

from core.files.atomic import write_json_atomic
from pipeline.planning.plan_file import load_plan, plan_path
from pipeline.runner.claude_runner import AgentError, AgentReply
from pipeline.stages.builder_run import build_attempt
from pipeline.stages.check_report import write_check_report
from pipeline.stages.check_run import check_attempt
from pipeline.stages.prepare import prepare_story
from tests.pipeline.stages.builder_setup import build_project
from tests.pipeline.stages.stage_setup import OK, RUN
from tests.pipeline.workspace.repo import git

OLD_TEST = "def test_old():\n    assert 1 == 1\n"
BUILDER_REPORT = "**Changed:** src/a.py\n**Checked:** none run\n**Not done:** nothing"
NEW_TEST = "def test_new():\n    assert 2 == 2\n"


def answer_of_tester(coverage=None, uncovered=None, defects=(), notes=()):
    cover = coverage if coverage is not None else {1: ["tests/test_new.py::test_new"]}
    return json.dumps(
        {
            "summary": "tested it",
            "coverage": [{"criterion": n, "tests": t} for n, t in cover.items()],
            "uncovered": [{"criterion": n, "reason": r} for n, r in (uncovered or {}).items()],
            "suspected_defects": list(defects),
            "notes": list(notes),
        }
    )


def answer_of_reviewer(met=(True,), verdict=None, problems=(), notes=()):
    return json.dumps(
        {
            "verdict": verdict or ("pass" if all(met) and not problems else "fail"),
            "criteria": [
                {"criterion": n, "met": m, "evidence": f"evidence {n}"}
                for n, m in enumerate(met, start=1)
            ],
            "problems": list(problems),
            "notes": list(notes),
        }
    )


def _script(texts, default):
    """The answers an agent gives in turn: a list is used in order, the last one repeats."""
    return list(texts) if isinstance(texts, list) else [texts or default]


class TeamRunner:
    """Fake Claude Code: each agent writes its files and answers with its scripted text."""

    def __init__(self, *, builder=None, tester=None, reviewer=None, tester_text=None,
                 reviewer_text=None, errors=None):  # fmt: skip
        self.writes = {
            "builder": {"src/a.py": "x = 1\n"} if builder is None else builder,
            "tester": {"tests/test_new.py": NEW_TEST} if tester is None else tester,
            "reviewer": reviewer or {},
        }
        self.answers = {
            "builder": [BUILDER_REPORT],
            "tester": _script(tester_text, answer_of_tester()),
            "reviewer": _script(reviewer_text, answer_of_reviewer()),
        }
        self.errors = errors or {}
        self.requests = []

    def of(self, role):
        return [r for r in self.requests if r.agent == role]

    def run(self, request):
        self.requests.append(request)
        role = request.agent
        if role in self.errors:
            raise AgentError(self.errors[role])
        for name, content in self.writes[role].items():
            path = request.cwd / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        texts = self.answers[role]
        text = texts.pop(0) if len(texts) > 1 else texts[0]
        return AgentReply(
            text, request.session_id, cost_usd=0.1, turns=3, duration_ms=2000,
            input_tokens=10, output_tokens=5, cache_tokens=1, model_used="claude-sonnet",
        )  # fmt: skip


def team_project(tmp_path, *, files=("src/a.py",), verify=(OK,), checks=(), criteria=("It works.",),
                 old_test=True, extra=None):  # fmt: skip
    """(repo, settings, engine): a prepared run whose story branch has a tests/ folder."""
    repo, config, engine = build_project(tmp_path, checks=checks, prepared=False)
    if old_test:
        (repo / "tests").mkdir()
        (repo / "tests" / "test_old.py").write_text(OLD_TEST, encoding="utf-8")
        git(repo, "add", "tests/test_old.py")
        git(repo, "commit", "-q", "-m", "an old test")
    for name, text in (extra or {}).items():  # more tracked files, as {path: text}
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", f"add {name}")
    plan = load_plan(repo, RUN)
    plan["config"]["base_commit"] = git(repo, "rev-parse", "HEAD")
    plan["tasks"][0].update(
        files=list(files), verification=list(verify), acceptance_criteria=list(criteria)
    )
    write_json_atomic(plan_path(repo, RUN), plan)
    prepare_story(config, RUN)
    return repo, config, engine


def built_and_checked(repo, config, engine, runner, key="SMT-62"):
    """Run the Builder and the checks and write the check report, as `task` does."""
    build_attempt(config, RUN, key, runner, engine=engine)
    report = check_attempt(config, RUN, key, engine=engine)
    write_check_report(repo, RUN, report)
    return report
