"""Start a run over: forget what its builds wrote, so that story builds every task again.

reset_run   remove the run's database rows (attempts, agent runs, checks, merges, budget) and its
            report folders, keeping plan.json. Refused while the run still has a branch or a
            worktree, or while a story loop holds its lock

It never touches Git: the person deletes the branches (clean first removes the worktrees), because
a branch may hold work worth keeping and only a person can tell. The refusal names each one. The
story loop trusts the database, and merges a Done attempt from its saved commit even when the
branch is gone, so rows left behind would silently bring the old code back.
"""

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine

from core.db import get_session, init_db
from core.db.repositories.run_reset import reset_run as reset_rows
from core.runs import run_directory
from core.settings import Settings
from pipeline.stages.errors import BuildError
from pipeline.stages.prepare import approved_plan, project_root
from pipeline.workspace import layout, worktrees
from pipeline.workspace.git import run_git
from pipeline.workspace.lock import run_lock

KEEP = ("plan.json", "story.lock")  # the lock is ours while we work, and removes itself
TRIES, PAUSE_SECONDS = 5, 0.5  # Windows, Explorer and OneDrive hold a folder for a moment


@dataclass
class ResetResult:
    run_id: str
    rows: dict[str, int] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)  # (name, why it could not go)

    def text(self) -> str:
        counts = ", ".join(f"{n} {name.replace('_', ' ')}" for name, n in self.rows.items() if n)
        lines = [
            f"Run {self.run_id} is {'NOT fully reset' if self.kept else 'reset'}.",
            f"Database rows removed: {counts or 'none'}.",
        ]
        lines.append(f"Removed from the run's folder: {', '.join(self.removed) or 'nothing'}.")
        if self.kept:
            lines.append("NOT removed (something holds them):")
            lines += [f"  {name}: {why}" for name, why in self.kept]
            lines.append(
                "Close Explorer windows open on the run's folder and pause OneDrive, "
                "then run reset again: it finishes what is left."
            )
        else:
            lines.append("Kept: plan.json. Next: prepare, then story.")
        return "\n".join(lines)


def _remove(path: Path) -> str | None:
    """Remove a file or folder, trying a few times. None when it is gone, else why not."""
    for attempt in range(TRIES):
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            problem = exc.strerror or str(exc)
            if attempt < TRIES - 1:
                time.sleep(PAUSE_SECONDS)
    return problem


def _leftovers(settings: Settings, root, run_id: str) -> list[str]:
    """What still belongs to the run in Git: worktrees to clean, branches to delete."""
    wanted = f"refs/heads/{layout.story_branch(run_id)}", f"refs/heads/agent-attempt/{run_id}"
    branches = run_git(root, "for-each-ref", "--format=%(refname:short)", *wanted).splitlines()
    folder = layout.run_worktrees(settings.worktrees_dir, run_id).resolve()
    trees = [
        info for info in worktrees.list_worktrees(root)[1:] if folder in info.path.resolve().parents
    ]
    found = []
    if trees:
        found.append(f"{len(trees)} worktree(s) remain: run  clean {run_id} --discard")
    found += [f"git branch -D {name}" for name in sorted(branches)]
    return found


def reset_run(settings: Settings, run_id: str, engine: Engine | None = None) -> ResetResult:
    """Reset the run. BuildError: it is not an approved run, or Git still holds its work."""
    root = project_root(settings)
    approved_plan(root, run_id)
    left = _leftovers(settings, root, run_id)
    if left:
        raise BuildError(
            f"Run {run_id} still has work in Git. Remove it first (inside the project, "
            "git -C <project>), then run reset again:\n" + "\n".join(f"- {text}" for text in left)
        )
    folder = run_directory(root, run_id)
    result = ResetResult(run_id)
    with run_lock(folder):
        with get_session(init_db(engine)) as session:
            result.rows = reset_rows(session, run_id)
        for path in sorted(folder.iterdir()):
            if path.name in KEEP:
                continue
            problem = _remove(path)
            if problem is None:
                result.removed.append(path.name)
            else:
                result.kept.append((path.name, problem))
    return result
