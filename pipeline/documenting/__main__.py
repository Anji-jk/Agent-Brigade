"""The documentation tools from the command line, for the project in .env:

python -m pipeline.documenting kind <run_id>
    which task of the run's plan is the documentation task (free; exit 0 found, 2 none)

python -m pipeline.documenting facts <run_id>
    collect what the run did from the database, Git and the plan, print it and write
    <project>/.agent-brigade/runs/<run_id>/docs/facts.json (free; no agent)

python -m pipeline.documenting review <run_id> <KEY> [--number N]
    ask only the Documentation Reviewer about the attempt as its files are now (it costs a
    little; nothing is committed or recorded; exit 0 the Reviewer passes it, 2 it does not)

Exit codes: 0 done, 1 refused or could not read the plan, 2 the plan has no documentation task.
"""

import argparse
import sys
from pathlib import Path

from core.db import get_engine, init_db
from core.settings import get_settings
from pipeline.documenting.doc_kind import documentation_keys
from pipeline.documenting.doc_review_only import review_only
from pipeline.documenting.facts import FactsError, collect_facts
from pipeline.documenting.facts_format import format_facts
from pipeline.documenting.facts_model import write_facts
from pipeline.planning.plan_file import PlanFileError, load_plan
from pipeline.runner.claude_runner import AgentError, AgentRunner, ClaudeCliRunner
from pipeline.stages.errors import BuildError
from pipeline.workspace.git import GitError, repository_root


def _project_root() -> Path:
    path = get_settings().project_path
    if path is None:
        raise GitError("BRIGADE_PROJECT_PATH is empty in .env.")
    return repository_root(path)


def kind(run_id: str) -> int:
    tasks = load_plan(_project_root(), run_id)["tasks"]
    keys = documentation_keys(tasks)
    for task in tasks:
        mark = "documentation" if task.get("jira_key") in keys else "build"
        print(f"  {task.get('jira_key')}  {mark:<13}  {task.get('title')}")
    if not keys:
        print("No documentation task in this plan: the story report is written instead.")
        return 2
    return 0


def facts(run_id: str) -> int:
    root = _project_root()
    collected = collect_facts(init_db(get_engine()), root, run_id)
    path = write_facts(root, collected)
    print(format_facts(collected))
    print(f"Facts file: {path}")
    return 0


def review(run_id: str, key: str, number: int | None, runner: AgentRunner) -> int:
    engine = init_db(get_engine())
    done = review_only(get_settings(), run_id, key, runner, number, engine=engine)
    print(done.text)
    return 0 if done.status == "done" else 2


def main(argv: list[str] | None = None, runner: AgentRunner | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.documenting")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("kind", help="which task is the documentation task").add_argument("run_id")
    sub.add_parser("facts", help="collect and write the facts of a run").add_argument("run_id")
    one = sub.add_parser("review", help="ask only the Documentation Reviewer")
    one.add_argument("run_id")
    one.add_argument("key")
    one.add_argument("--number", type=int, default=None, help="attempt number (default newest)")
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            return review(args.run_id, args.key, args.number, runner or ClaudeCliRunner())
        return (kind if args.command == "kind" else facts)(args.run_id)
    except (GitError, PlanFileError, FactsError, BuildError, AgentError, ValueError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())