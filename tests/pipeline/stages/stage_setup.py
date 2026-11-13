"""A project with an approved plan, for the stage tests: its lines are small Python programs."""

import sys

from pipeline.planning.plan_file import save_plan
from tests.pipeline.planning.test_plan_file import document, task
from tests.pipeline.planning.test_readiness import settings
from tests.pipeline.workspace.repo import git, make_repo

RUN = "SMT-61-20261113-6b1a"
PY = f'"{sys.executable}"'


def line(code: str, *more: str) -> str:
    """A command line that runs this Python code."""
    return " ".join([PY, "-c", f'"{code}"', *more])


MAKE_FILE = line("open('made.txt', 'w').write('x')")
OK = line("print(1)")
FAIL = line("import sys; sys.exit(3)")
NO_TESTS = line("import sys; sys.exit(5)", "pytest")


def approved_project(tmp_path, *, setup=(), checks=(), status="approved"):
    """(repo, settings, base commit): a plan of two tasks, approved unless `status` says not."""
    repo = make_repo(tmp_path / "proj")
    base = git(repo, "rev-parse", "HEAD")
    plan = document(task("T1", jira_key="SMT-62"), task("T2", jira_key="SMT-63", depends_on=["T1"]))
    plan["config"] = {"branch": f"agent/{RUN}", "base_ref": "main", "base_commit": base}
    plan["commands"] = {"setup": list(setup), "project_checks": list(checks)}
    plan["approval"] = {"status": status, "jira_links": []}
    save_plan(repo, RUN, plan)
    config = settings(tmp_path, project_path=repo).model_copy(
        update={"worktree_root": tmp_path / "bw"}
    )
    return repo, config, base
