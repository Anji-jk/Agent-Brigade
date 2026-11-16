"""Is there a place for tests: does the Tester have anything to work with, and if not, why.

A file is first a candidate by its name or folder (pipeline/checks/testfiles.py), then it must
really declare a test. A script in a folder called test, or a helper such as conftest.py, is
named like a test but holds none, so it does not count. A test the task itself lists counts
without being read: the Tester is there to write it.

find_place   the answer, with the files that were looked at
"""

from dataclasses import dataclass, field
from pathlib import Path

from pipeline.checks.testfiles import holds_a_test, is_test_path, listed_test_paths

MAX_FILES = 300  # candidates read at most
MAX_BYTES = 200_000  # of each, from its start
SHOWN = 5  # names printed in the reason


@dataclass
class Place:
    listed: list[str] = field(default_factory=list)  # test files the task itself lists
    real: list[str] = field(default_factory=list)  # named like tests and really holding one
    empty: list[str] = field(default_factory=list)  # named like tests but holding none

    @property
    def found(self) -> bool:
        return bool(self.listed or self.real)

    def reason(self) -> str:
        """Why there is no place, with what was looked at. Empty when there is one."""
        if self.found:
            return ""
        if not self.empty:
            return "the task lists no test file and the project has no test files."
        shown = ", ".join(self.empty[:SHOWN]) + (", ..." if len(self.empty) > SHOWN else "")
        return (
            f"the task lists no test file, and none of the project's {len(self.empty)} "
            f"test-named file(s) declares a test ({shown})."
        )


def _text(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(MAX_BYTES).decode("utf-8", errors="ignore")
    except OSError:
        return ""


def find_place(worktree: Path, task_files: list[str], paths: list[str]) -> Place:
    """Look for a place for tests: the task's own test files, else real tests in `paths`."""
    place = Place(listed=listed_test_paths(task_files))
    if place.listed:
        return place
    for path in [p for p in dict.fromkeys(paths) if is_test_path(p)][:MAX_FILES]:
        (place.real if holds_a_test(_text(worktree / path)) else place.empty).append(path)
    return place
