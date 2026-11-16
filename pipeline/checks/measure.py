"""What the orchestrator measures about one attempt before any agent judges it. No agent runs.

measure_attempt   the changed files from Git, those outside the task's Files, any protected
                  path touched, then the task's own Verify lines run in the attempt worktree

Only two things stop an attempt (BLOCKING): nothing changed, or a protected path changed. Files
outside the task's list and the Verify results are facts handed to the Reviewer, who judges them
(a Verify line may fail for a reason the Builder did not cause, such as a failing baseline).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.checks.paths import extra_files, protected
from pipeline.workspace.commands import CommandResult, run_command
from pipeline.workspace.git import changed_paths

BLOCKING = ("changes", "protected")  # the check kinds whose failure fails the attempt


@dataclass
class CheckReport:
    key: str
    number: int
    worktree: str
    changed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)  # changed, but not in the task's Files
    protected: list[str] = field(default_factory=list)
    verify: list[CommandResult] = field(default_factory=list)
    verify_lines: int = 0  # how many the task lists (the results hold the ones that ran)

    @property
    def verify_ran(self) -> bool:
        return not self.protected

    @property
    def passed(self) -> bool:
        """No blocking check failed. Verify results are not part of it: the Reviewer reads them."""
        return not self.failures()

    def failures(self) -> list[str]:
        found = []
        if not self.changed:
            found.append("The Builder changed no files.")
        if self.protected:
            found.append("A protected path was changed: " + ", ".join(self.protected))
        return found

    def failed_verify(self) -> list[str]:
        """The Verify lines that failed or timed out, for the Reviewer."""
        return [result.command for result in self.verify if not result.passed]


def verify_lines(task: dict[str, Any]) -> list[str]:
    """The task's Verify lines, each once, in order."""
    return list(dict.fromkeys(line for line in task.get("verification", []) if line.strip()))


def measure_attempt(
    worktree: Path, task: dict[str, Any], key: str, number: int, *, timeout: int
) -> CheckReport:
    """Measure the worktree. A protected change stops it before anything is run."""
    lines = verify_lines(task)
    report = CheckReport(key, number, str(worktree), verify_lines=len(lines))
    report.changed = changed_paths(worktree)
    report.extra = extra_files(report.changed, task.get("files", []))
    report.protected = protected(report.changed, task.get("files", []))
    if report.verify_ran:
        report.verify = [run_command(line, worktree, timeout=timeout) for line in lines]
    return report
