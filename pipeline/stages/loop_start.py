"""What the Start button runs: prepare the run if it is not prepared yet, then the story loop.

A run is prepared once (story branch, story worktree, setup, baseline). A failed SETUP stops
here, before an agent is paid for: nothing can build without it. A baseline that already fails
is the project's own state on its base commit, not a fault of the build, so it is reported and
the story goes on (the Reviewer is shown the checks that fail; see the design notes on a
baseline that already fails).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.settings import Settings
from pipeline.runner.claude_runner import AgentRunner
from pipeline.stages.prepare import PrepareError, prepare_story, project_root
from pipeline.stages.prepare_report import FAILED, Prepared
from pipeline.stages.story_loop import run_story
from pipeline.workspace import layout
from pipeline.workspace.worktrees import list_worktrees


class LoopStartError(PrepareError):
    """The run could not be started. The message says why and what was left behind."""


@dataclass
class LoopRun:
    story: Any  # the StoryResult of the loop
    prepared: Prepared | None = None  # what preparing did, when this start had to prepare
    warnings: list[str] = field(default_factory=list)


def is_prepared(settings: Settings, run_id: str) -> bool:
    """Is the run's story worktree there? (The branch alone is not enough: merges need it.)"""
    wanted = layout.story_worktree(settings.worktrees_dir, run_id).resolve()
    return any(info.path.resolve() == wanted for info in list_worktrees(project_root(settings)))


def start_loop(
    settings: Settings,
    run_id: str,
    runner: AgentRunner,
    engine: Any = None,
    *,
    prepare: Callable[..., tuple[Prepared, Any]] = prepare_story,
    run: Callable[..., Any] = run_story,
) -> LoopRun:
    done = LoopRun(story=None)
    if not is_prepared(settings, run_id):
        done.prepared, _ = prepare(settings, run_id)
        broken = [step for step in done.prepared.setup if step.status == FAILED]
        if broken:
            raise LoopStartError(
                f"Setup failed: {broken[0].line} (exit {broken[0].exit_code}). Nothing was built; "
                f"python -m pipeline.stages clean {run_id} removes the worktree, then start again."
            )
        done.warnings = [
            f"Already failing before any agent worked: {step.line} (exit {step.exit_code})."
            for step in done.prepared.baseline
            if step.status == FAILED
        ]
    done.story = run(settings, run_id, runner, engine)
    return done