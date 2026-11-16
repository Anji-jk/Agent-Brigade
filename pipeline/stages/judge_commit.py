"""Which files an attempt is made of, the diff the Reviewer reads, and the commit.

An attempt is the files the Builder changed (from check) plus the files the Tester wrote. A file
a check or a test run left behind is not part of it: it is reported and never committed. Staging
is exact (stage_paths); a commit is made only when the attempt was judged Done.
"""

from pipeline.stages.stage_inputs import Inputs
from pipeline.workspace.commit import commit_message, commit_staged, stage_paths, staged_diff
from pipeline.workspace.git import changed_paths


def attempt_paths(inputs: Inputs) -> tuple[list[str], list[str]]:
    """(the attempt's files that differ from HEAD now, other changed files left behind)."""
    wanted = set((inputs.check or {}).get("changed", []))
    if inputs.test and inputs.test.get("ran"):
        wanted |= set(inputs.test.get("wrote", []))
    now = changed_paths(inputs.worktree)
    return [path for path in now if path in wanted], [path for path in now if path not in wanted]


def diff_for_review(inputs: Inputs) -> str:
    """Stage the attempt's files and return their diff against HEAD."""
    paths, _ = attempt_paths(inputs)
    stage_paths(inputs.worktree, paths)
    return staged_diff(inputs.worktree)


def commit_attempt(inputs: Inputs) -> tuple[str, list[str]]:
    """Commit the attempt's files. Returns (the commit id, files left behind uncommitted)."""
    paths, left_over = attempt_paths(inputs)
    stage_paths(inputs.worktree, paths)
    subject, body = commit_message(inputs.key, inputs.task["title"], inputs.criteria)
    return commit_staged(inputs.worktree, subject, body), left_over
